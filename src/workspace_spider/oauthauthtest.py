from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Set OAuth scopes (Google Drive API Read-Only)
SCOPES = ["https://www.googleapis.com/auth/drive.metadata.readonly"]

# Authenticate using OAuth 2.0
flow = InstalledAppFlow.from_client_secrets_file("../../secrets/client_secret.json", SCOPES)
creds = flow.run_local_server(port=0)

# Build the Drive API client
service = build("drive", "v3", credentials=creds)

# Test: List 10 files from the authenticated user's Drive
results = service.files().list(pageSize=10, fields="files(id, name)").execute()
files = results.get("files", [])

print("\n=== Drive Files ===")
if not files:
    print("No files found.")
else:
    for file in files:
        print(f"{file['name']} ({file['id']})")
