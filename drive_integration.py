"""
drive_integration.py — Google Drive for Raj v4.0
File attachments for templates, link validation.
"""

import os
import pickle
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ['https://www.googleapis.com/auth/drive.readonly', 'https://www.googleapis.com/auth/drive.file']

class DriveManager:
    def __init__(self, credentials_path='credentials.json', token_path='drive_token.pickle'):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        self._authenticate()

    def _authenticate(self):
        creds = None
        if os.path.exists(self.token_path):
            with open(self.token_path, 'rb') as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_path):
                    print("[Drive] credentials.json not found. Drive integration disabled.")
                    return
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(self.token_path, 'wb') as token:
                pickle.dump(creds, token)

        self.service = build('drive', 'v3', credentials=creds)
        print("[Drive] Connected to Google Drive")

    def list_files(self, folder_id=None, query=None, page_size=100):
        """List files in Drive."""
        if not self.service:
            return []

        q = query or ""
        if folder_id:
            q += f"'{folder_id}' in parents" if not q else f" and '{folder_id}' in parents"

        results = self.service.files().list(
            q=q, pageSize=page_size,
            fields="nextPageToken, files(id, name, mimeType, webViewLink, modifiedTime)").execute()

        return results.get('files', [])

    def get_file_url(self, file_id):
        """Get direct download/view URL for a file."""
        if not self.service:
            return None

        try:
            file = self.service.files().get(fileId=file_id, fields='id, name, webViewLink, webContentLink').execute()
            return {
                'id': file['id'],
                'name': file['name'],
                'view_url': file.get('webViewLink', ''),
                'download_url': file.get('webContentLink', '')
            }
        except:
            return None

    def validate_link(self, file_id):
        """Check if a Drive file link is still valid."""
        if not self.service:
            return False

        try:
            self.service.files().get(fileId=file_id, fields='id').execute()
            return True
        except:
            return False

    def upload_file(self, filepath, filename=None, folder_id=None):
        """Upload a file to Drive."""
        if not self.service:
            return None

        try:
            name = filename or os.path.basename(filepath)
            file_metadata = {'name': name}
            if folder_id:
                file_metadata['parents'] = [folder_id]

            media = MediaFileUpload(filepath, resumable=True)
            file = self.service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()

            return {
                'id': file['id'],
                'name': name,
                'url': file.get('webViewLink', '')
            }
        except Exception as e:
            print(f"[Drive] Upload failed: {e}")
            return None
