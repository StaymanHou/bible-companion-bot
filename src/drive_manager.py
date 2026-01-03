import os
import yaml
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
import io

logger = logging.getLogger(__name__)

class GoogleDriveManager:
    def __init__(self, credentials_path=None):
        self.scopes = ['https://www.googleapis.com/auth/drive']
        self.credentials_path = credentials_path or os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
        self.service = self._authenticate()

    def _authenticate(self):
        try:
            if not self.credentials_path:
                logger.warning("No credentials path provided. Drive integration will fail if not mocked.")
                return None
            
            creds = service_account.Credentials.from_service_account_file(
                self.credentials_path, scopes=self.scopes)
            return build('drive', 'v3', credentials=creds)
        except Exception as e:
            logger.error(f"Failed to authenticate with Google Drive: {e}")
            return None

    def get_service_account_email(self):
        """Extracts the client email from the service account credentials file."""
        try:
            if not self.credentials_path:
                return "Unknown (No credentials path)"
            
            with open(self.credentials_path, 'r') as f:
                data = yaml.safe_load(f) # JSON is valid YAML
                return data.get('client_email', 'Unknown')
        except Exception as e:
            logger.error(f"Error reading credentials file: {e}")
            return "Unknown"

    def list_files_in_folder(self, folder_id):
        """Lists files in a specific Google Drive folder."""
        if not self.service: return []
        try:
            results = self.service.files().list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="files(id, name, mimeType)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True).execute()
            return results.get('files', [])
        except Exception as e:
            logger.error(f"Error listing files: {e}")
            return []

    def read_md_file(self, file_id):
        """Reads a Markdown file and parses YAML frontmatter."""
        if not self.service: return None, None
        try:
            request = self.service.files().get_media(fileId=file_id, supportsAllDrives=True)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            
            content = fh.getvalue().decode('utf-8')
            
            # Parse Frontmatter
            if content.startswith('---'):
                parts = content.split('---', 2)
                if len(parts) >= 3:
                    frontmatter = yaml.safe_load(parts[1])
                    body = parts[2]
                    return frontmatter, body.strip()
            
            return {}, content

        except Exception as e:
            logger.error(f"Error reading file {file_id}: {e}")
            return None, None

    def write_md_file(self, folder_id, filename, frontmatter, body, file_id=None):
        """Creates or updates a Markdown file with YAML frontmatter."""
        if not self.service: return None
        
        content = "---\n" + yaml.dump(frontmatter) + "---\n\n" + body
        
        file_metadata = {
            'name': filename,
            'mimeType': 'text/markdown'
        }
        
        media = MediaIoBaseUpload(io.BytesIO(content.encode('utf-8')),
                                  mimetype='text/markdown',
                                  resumable=True)
        
        try:
            # Upsert Logic: If file_id is missing, try to find it by name
            if not file_id:
                file_id = self.get_file_id_by_name(folder_id, filename)

            if file_id:
                # Update existing file
                file = self.service.files().update(
                    fileId=file_id,
                    media_body=media,
                    supportsAllDrives=True).execute()
                return file.get('id') or file_id
            else:
                # Create new file
                file_metadata['parents'] = [folder_id]
                file = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id',
                    supportsAllDrives=True).execute()
                return file.get('id')
        except Exception as e:
            logger.error(f"Error writing file {filename}: {e}")
            raise e # Re-raise to let caller handle quota errors

    def delete_file(self, file_id):
        """Deletes a file from Google Drive."""
        if not self.service: return False
        try:
            self.service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
            return True
        except Exception as e:
            logger.error(f"Error deleting file {file_id}: {e}")
            return False

    def get_file_id_by_name(self, folder_id, filename):
        """Finds a file ID by name within a folder."""
        files = self.list_files_in_folder(folder_id)
        for f in files:
            if f['name'] == filename:
                return f['id']
        return None
