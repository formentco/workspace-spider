import requests
import json
import re
import time
import pandas as pd
import logging
import os
import base64
from dotenv import load_dotenv
import colorlog
from tenacity import retry, stop_after_attempt, wait_exponential


# Configure Coloured Logging
log_formatter = colorlog.ColoredFormatter(
    "%(log_color)s%(asctime)s - %(levelname)s - %(message)s",
    log_colors={
        "DEBUG": "cyan",
        "INFO": "green",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "bold_red",
    }
)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

file_handler = logging.FileHandler("linkfinderconfluence.log", mode="w")
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

logging.basicConfig(level=logging.INFO, handlers=[console_handler, file_handler])
logger = logging.getLogger("confluence_logger")


# Load environment variables from .env file
load_dotenv()

output_dir=os.getenv("OUTPUT_DIR","data")

# Read credentials from environment variables
CONFLUENCE_BASE_URL = os.getenv("CONFLUENCE_BASE_URL")
USERNAME = os.getenv("USERNAME")
API_TOKEN = os.getenv("API_TOKEN")


logger.debug(f"Base URL: {CONFLUENCE_BASE_URL}")
logger.debug(f"Username: {USERNAME}")
logger.debug(f"API Token Present: {'Yes' if API_TOKEN else 'No'}")


if not CONFLUENCE_BASE_URL or not USERNAME or not API_TOKEN:
    raise ValueError("Missing required environment variables. Ensure CONFLUENCE_BASE_URL, USERNAME, and API_TOKEN are set in the .env file.")


# Encode authentication credentials
auth_string = f"{USERNAME}:{API_TOKEN}"
auth_b64 = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")

HEADERS = {
    "Authorization": f"Basic {auth_b64}",
    "Content-Type": "application/json",
}

# Regular expressions to find Google Drive links
GOOGLE_DRIVE_HARDLINK_REGEX = r"https?://(?:drive|docs)\.google\.com\S+"
GOOGLE_DRIVE_SMARTLINK_REGEX = r'<ac:structured-macro[^>]*ac:name="inline-card"[^>]*data-card-url="([^"]*drive\.google\.com[^"]*)"'

# Retry logic for API calls (exponential backoff)
@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10))
def confluence_request(url, params=None):
    logging.info(f"Fetching URL: {url} with params {params}")
    response = requests.get(url, headers=HEADERS, params=params)

    if response.status_code == 429:  # Rate limit hit
        logging.warning("Rate limit exceeded, retrying...")
        raise Exception("Rate limit exceeded")

    if response.status_code != 200:
        logging.error(f"Error {response.status_code}: {response.text}")
        response.raise_for_status()

    return response.json()

# Get all spaces (Confluence sites)
def get_all_spaces():
    spaces = []
    url = f"{CONFLUENCE_BASE_URL}/rest/api/space"
    params = {"limit": 100}

    while url:
        try:
            data = confluence_request(url, params)
            if not data.get("results"):
                logging.warning("No spaces found.")
                return []

            spaces.extend(data["results"])
            url = data["_links"].get("next")
            if url:
                url = CONFLUENCE_BASE_URL + url
        except Exception as e:
            logging.error(f"Failed to fetch spaces: {e}")
            break

    for space in spaces:
        logging.info(f"Space Key: {space['key']}, Name: {space['name']}")

    # Define the file path using the output directory
    output_file = os.path.join(output_dir, "spaces_list.csv")

    # Write space details to a file
    with open(output_file, "w") as f:
        f.write("Space Key,Space Name\n")
        for space in spaces:
            f.write(f"{space['key']},{space['name']}\n")

    logging.info(f"Spaces list saved to: {output_file}")
    logging.info(f"Total spaces found: {len(spaces)}")

    return spaces

# Get all published pages for a given space
def get_all_pages(space_key):
    pages = []
    url = f"{CONFLUENCE_BASE_URL}/rest/api/content"
    params = {
        "type": "page",
        "spaceKey": space_key,
        "expand": "body.storage,version",
        "status": "current",
        "limit": 100
    }

    while url:
        try:
            data = confluence_request(url, params)
            if not data.get("results"):
                logging.warning(f"No pages found in space: {space_key}")
                return []

            pages.extend(data["results"])
            url = data["_links"].get("next")
            if url:
                url = CONFLUENCE_BASE_URL + url
        except Exception as e:
            logging.error(f"Failed to fetch pages for space {space_key}: {e}")
            break

    logging.info(f"Total pages found in {space_key}: {len(pages)}")
    return pages

# Extract Google Drive links and determine if they are Smart Links or Hardcoded
def extract_google_drive_links(page_content):
    hard_links = re.findall(GOOGLE_DRIVE_HARDLINK_REGEX, page_content)
    smart_links = re.findall(GOOGLE_DRIVE_SMARTLINK_REGEX, page_content)

    extracted_links = []
    for link in hard_links:
        extracted_links.append((link, "Hardcoded"))
    for link in smart_links:
        extracted_links.append((link, "Smart Link"))

    return extracted_links

# Process all spaces and pages
def process_confluence():
    results = []
    spaces = get_all_spaces()
    if not spaces:
        logging.error("No spaces retrieved. Exiting script.")
        return

    for space in spaces:
        space_key = space["key"]
        logging.debug(f"Processing space: {space_key}")

        pages = get_all_pages(space_key)
        if not pages:
            logging.warning(f"No pages found in space {space_key}. Skipping.")
            continue

        for page in pages:
            page_id = page["id"]
            page_title = page["title"]
            last_modified = page["version"]["when"]
            page_url = f"{CONFLUENCE_BASE_URL}/spaces/{space_key}/pages/{page_id}/{page_title.replace(' ', '-')}"

            logging.debug(f"Processing page: {page_title} ({page_id})")

            try:
                content = page["body"]["storage"]["value"]
                links = extract_google_drive_links(content)

                if not links:
                    logging.debug(f"No Google Drive links found in {page_title}")
                    continue

                for link, link_type in links:
                    results.append([space_key, page_title, link, link_type, page_url, last_modified])
                    logging.debug(f"Found {link_type} link in {page_title}: {link}")

            except Exception as e:
                logging.error(f"Error processing page {page_title} ({page_id}): {e}")
                results.append([space_key, page_title, "ERROR", "N/A", str(e), "N/A"])

    # Convert results to DataFrame and save
    df = pd.DataFrame(results, columns=["Site", "Page", "Link", "Link Type", "Text", "Last Modified"])

    if df.empty:
        logging.warning("No Google Drive links found in any pages.")
    else:
        out_file=os.path.join(output_dir, "confluence_links.csv")
        df.to_csv(out_file, index=False)
        logging.info("Data saved to: %s", out_file)

# Run script
if __name__ == "__main__":
    process_confluence()
