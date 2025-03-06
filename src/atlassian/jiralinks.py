import requests
import json
import re
import os
import base64
import pandas as pd
import logging
import colorlog
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

# Configure logging
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
file_handler = logging.FileHandler("linkfinder_jira.log", mode="w")
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[console_handler, file_handler])
logger = logging.getLogger("jira_logger")

# Load environment variables
load_dotenv()
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL")
USERNAME = os.getenv("JIRA_USERNAME")
API_TOKEN = os.getenv("JIRA_API_TOKEN")

# Get the output directory (default to 'data' if not set)
output_dir = os.getenv("OUTPUT_DIR", "data")

auth_string = f"{USERNAME}:{API_TOKEN}"
auth_b64 = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")
HEADERS = {
    "Authorization": f"Basic {auth_b64}",
    "Content-Type": "application/json",
}

# Google Drive link regex patterns
#GOOGLE_DRIVE_HARDLINK_REGEX = r"https?://(?:drive|docs)\.google\.com/(?:document|spreadsheets|presentation|drive|file)/\S+"
GOOGLE_DRIVE_HARDLINK_REGEX = r"https?://(?:drive|docs)\.google\.com/\S+"

@retry(stop=stop_after_attempt(5), wait=wait_exponential(min=2, max=10))
def jira_request(url, params=None):
    logger.info(f"Fetching URL: {url} with params {params}")
    response = requests.get(url, headers=HEADERS, params=params)
    if response.status_code == 429:
        logger.warning("Rate limit exceeded, retrying...")
        raise Exception("Rate limit exceeded")
    if response.status_code != 200:
        logger.error(f"Error {response.status_code}: {response.text}")
        response.raise_for_status()
    return response.json()

# Get all Jira projects
def get_all_projects():
    url = f"{JIRA_BASE_URL}/rest/api/3/project"
    logger.debug(f"Requesting projects from {url}")
    return jira_request(url)

# Get all issues for a given project
def get_all_issues(project_key):
    issues = []
    start_at = 0
    max_results = 100

    while True:
        url = f"{JIRA_BASE_URL}/rest/api/3/search"
        params = {
            "jql": f"project={project_key}",
            "startAt": start_at,
            "maxResults": max_results,
            "fields": "summary,description,comment,issuelinks,customfield_*,environment,issueType"
        }
        logger.debug(f"Fetching issues from {url} with params {params}")
        data = jira_request(url, params)
        batch_issues = data.get("issues", [])
        logger.info(f"Retrieved {len(batch_issues)} issues for project {project_key}")

        for issue in batch_issues:
            logger.debug(f"Raw issue data: {json.dumps(issue, indent=2)}")

        issues.extend(batch_issues)
        if len(batch_issues) < max_results:
            break
        start_at += max_results

    return issues

# Get remote links for an issue
def get_issue_links(issue_key):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/remotelink"
    logger.debug(f"Fetching remote links from {url}")
    try:
        data = jira_request(url)
        return [link.get("object", {}).get("url", "") for link in data if "object" in link]
    except Exception as e:
        logger.error(f"Failed to fetch remote links for {issue_key}: {e}")
        return []

#Extract all links
def extract_text_and_links(content):
    extracted_text = ""
    links = []

    if isinstance(content, dict):
        if "content" in content and isinstance(content["content"], list):
            for item in content["content"]:
                text, found_links = extract_text_and_links(item)
                extracted_text += text + " "
                links.extend(found_links)
        if "text" in content:
            extracted_text += content["text"] + " "
        if content.get("type") == "inlineCard" and "attrs" in content and "url" in content["attrs"]:
            links.append(content["attrs"]["url"])
        # Handle link marks
        if "marks" in content:
            for mark in content["marks"]:
                if mark.get("type") == "link" and "attrs" in mark and "href" in mark["attrs"]:
                    links.append(mark["attrs"]["href"])
    elif isinstance(content, list):
        for item in content:
            text, found_links = extract_text_and_links(item)
            extracted_text += text + " "
            links.extend(found_links)

    return extracted_text.strip(), links

# Process comments
def process_comments(comments):
    links = []
    for comment in comments:
        comment_body = comment.get("body", {})
        extracted_links = extract_google_drive_links(comment_body)
        links.extend(extracted_links)
    return links


#Use URL matching as simple process
def extract_google_drive_links(text_or_structure):
    if isinstance(text_or_structure, dict) or isinstance(text_or_structure, list):
        text, links = extract_text_and_links(text_or_structure)
    else:
        text = text_or_structure if isinstance(text_or_structure, str) else ""
        links = []

    # Find all URLs in the text
    url_pattern = r"https?://[^\s]+"
    all_urls = re.findall(url_pattern, text)

    # Filter for only Google Drive/Docs URLs
    google_links = []
    for url in all_urls:
        if "drive.google.com" in url or "docs.google.com" in url:
            google_links.append(url)

    # Add any links that were extracted from the structure
    for link in links:
        if "drive.google.com" in link or "docs.google.com" in link:
            google_links.append(link)

    return google_links

# Process all projects and issues
def process_jira():
    results = []
    projects = get_all_projects()
    if not projects:
        logger.error("No projects found. Exiting.")
        return

    for project in projects:
        project_key = project["key"]
        logger.info(f"Processing project: {project_key}")
        issues = get_all_issues(project_key)

        # Fetch all issues
        for issue in issues:
            logger.debug(f"All fields in issue {issue['key']}: {list(issue['fields'].keys())}")
            for field_name, field_value in issue['fields'].items():
                if field_value:  # Only log non-empty fields
                    logger.debug(f"Field {field_name} = {field_value}")

        for issue in issues:
            issue_key = issue["key"]
            summary = issue["fields"].get("summary", "N/A")
            description = issue["fields"].get("description", {})
            comments = issue["fields"].get("comment", {}).get("comments", [])

            logger.debug(f"Processing issue {issue_key}: {summary}")


            # Process summary
            summary_links = extract_google_drive_links(summary)
            for link in summary_links:
                results.append([project_key, issue_key, summary, link, "Summary"])
                logger.debug(f"Found Google Drive link in {issue_key} (Summary): {link}")

            # Process description
            description_links = extract_google_drive_links(description)
            for link in description_links:
                results.append([project_key, issue_key, summary, link, "Description"])
                logger.debug(f"Found Google Drive link in {issue_key} (Description): {link}")

            # Process comments
            for i, comment in enumerate(comments):
                comment_body = comment.get("body", {})
                comment_links = extract_google_drive_links(comment_body)
                for link in comment_links:
                    results.append([project_key, issue_key, summary, link, f"Comment {i+1}"])
                    logger.debug(f"Found Google Drive link in {issue_key} (Comment {i+1}): {link}")

            # Process custom fields
            for field_name, field_value in issue["fields"].items():
                if field_name.startswith("customfield_"):
                    # Check if field contains a Google Drive link
                    custom_field_links = extract_google_drive_links(field_value)
                    for link in custom_field_links:
                        results.append([project_key, issue_key, summary, link, f"Field: {field_name}"])
                        logger.debug(f"Found Google Drive link in {issue_key} (Field: {field_name}): {link}")

            # Process environment field (on all issues)
            environment = issue["fields"].get("environment")
            if environment:
                environment_links = extract_google_drive_links(environment)
                for link in environment_links:
                    results.append([project_key, issue_key, summary, link, "Environment"])
                    logger.info(f"Found Google Drive link in {issue_key} (Environment): {link}")

            # Handle remote links (web links in Jira)
            remote_links = get_issue_links(issue_key)
            logger.debug(f"Remote links for {issue_key}: {remote_links}")

            for link in remote_links:
                logger.debug(f"Processing remote link: {link}")

                if re.search(GOOGLE_DRIVE_HARDLINK_REGEX, link):
                    results.append([project_key, issue_key, summary, link, "Remote Link"])
                    logger.info(f"Found Google Drive link in {issue_key} (Remote Link): {link}")
                else:
                    logger.debug(f"Remote link {link} did not match Google Drive pattern")



    df = pd.DataFrame(results, columns=["Project", "Issue Key", "Summary", "Link", "Source"])
    if df.empty:
        logger.warning("No Google Drive links found in any issues.")
    else:
        output_file = os.path.join(output_dir, "jira_google_drive_links.csv")
        df.to_csv(output_file, index=False)
        logger.info("Data saved to %s", output_file)

if __name__ == "__main__":
    process_jira()
