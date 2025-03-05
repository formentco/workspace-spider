import os
import json
import requests
from google.auth import credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

class DriveAnalyzer:
    def __init__(self, credentials_path):
        """
        Initialize Drive Analyzer with Workload Identity Federation

        :param credentials_path: Path to the JSON configuration file
        """
        self.credentials = self._get_credentials(credentials_path)
        self.drive_service = build('drive', 'v3', credentials=self.credentials)

    def _get_credentials(self, credentials_path):
        """
        Obtain credentials using Workload Identity Federation

        :param credentials_path: Path to the JSON configuration file
        :return: Authenticated credentials
        """
        try:
            # Load the JSON configuration file
            with open(credentials_path, 'r') as file:
                config = json.load(file)

            # Extract the necessary information from the configuration
            token_url = config['token_url']
            subject_token_type = config['subject_token_type']
            service_account_impersonation_url = config['service_account_impersonation_url']
            credential_source = config['credential_source']
            oidc_token_file = credential_source['file']

            # Obtain the OIDC token from the token URL
            response = requests.get(config['audience'])
            response.raise_for_status()
            oidc_token = response.text.strip()

            # Save the OIDC token to the specified file
            os.makedirs(os.path.dirname(oidc_token_file), exist_ok=True)
            with open(oidc_token_file, 'w') as token_file:
                token_file.write(oidc_token)

            # Create the credentials using the OIDC token and configuration
            creds = credentials.Credentials(
                token=None,
                token_uri=token_url,
                subject_token_type=subject_token_type,
                service_account_impersonation_url=service_account_impersonation_url,
                credential_source=credential_source,
                subject_token=oidc_token
            )

            # Refresh the credentials to obtain the access token
            creds.refresh(Request())

            return creds

        except Exception as e:
            print(f"Credential retrieval error: {e}")
            raise

    # Rest of the code remains the same
    ...

def main():
    # Path to your Google Workspace Workload Identity Federation configuration file
    CREDENTIALS_PATH = '../../secrets/clientlib.json'
    TARGET_USER_EMAIL = 'home@shoutworld.co.uk'

    try:
        analyzer = DriveAnalyzer(CREDENTIALS_PATH)
        drive_stats = analyzer.analyze_drive_statistics(TARGET_USER_EMAIL)

        print("Drive Analysis Results:")
        for key, value in drive_stats.items():
            print(f"{key}: {value}")

    except Exception as e:
        print(f"Analysis failed: {e}")

if __name__ == "__main__":
    main()