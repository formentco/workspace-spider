import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
import google.auth
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.auth import load_credentials_from_file

class DriveAnalyzer:
    def __init__(self, credentials_path):
        """
        Initialize Drive Analyzer with Workload Identity Federation

        :param credentials_path: Path to the downloaded configuration file
        """
        self.credentials = self._get_credentials(credentials_path)
        self.drive_service = build('drive', 'v3', credentials=self.credentials)

    def _get_credentials(self, credentials_path):
        """
        Obtain credentials using Workload Identity Federation

        :param credentials_path: Path to the configuration file
        :return: Authenticated credentials
        """
        try:
            # Load credentials using the configuration file
            credentials, project = google.auth.load_credentials_from_file(
                credentials_path,
                scopes=[
                    'https://www.googleapis.com/auth/drive',
                    'https://www.googleapis.com/auth/admin.directory.user'
                ]
            )

            return credentials

        except Exception as e:
            print(f"Credential retrieval error: {e}")
            raise

    def list_user_files(self, user_email):
        """
        List files for a specific user across the domain

        :param user_email: Email of the user to analyze
        :return: List of file metadata
        """
        try:
            results = self.drive_service.files().list(
                q=f"'{user_email}' in owners and trashed=false",
                spaces='drive',
                fields="files(id, name, mimeType, createdTime, modifiedTime, size, shared)"
            ).execute()

            return results.get('files', [])

        except Exception as e:
            print(f"Error listing files: {e}")
            return []

    def analyze_drive_statistics(self, user_email):
        """
        Perform comprehensive drive statistics analysis

        :param user_email: Email of the user to analyze
        :return: Dictionary of drive statistics
        """
        files = self.list_user_files(user_email)

        stats = {
            'total_files': len(files),
            'file_types': {},
            'total_size': 0,
            'shared_files': 0
        }

        for file in files:
            mime_type = file.get('mimeType', 'unknown')
            file_size = int(file.get('size', 0))

            # Count file types
            stats['file_types'][mime_type] = stats['file_types'].get(mime_type, 0) + 1

            # Aggregate file size
            stats['total_size'] += file_size

            # Count shared files
            if file.get('shared', False):
                stats['shared_files'] += 1

        return stats

def main():
    # Path to your downloaded Workload Identity Federation configuration file
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