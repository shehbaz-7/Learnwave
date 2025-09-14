# C:\Users\nikhi\Downloads\PDFIntelligence\Learnwave\drive_service.py (FINAL)

import os
import io
import logging
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from google_auth import authenticate_google

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class DriveService:
    def __init__(self):
        """
        Initializes the DriveService by authenticating the user
        and creating the Google Drive API service object.
        """
        creds = authenticate_google()
        if not creds:
            raise Exception("Failed to authenticate Google account. Cannot initialize DriveService.")
        self.service = build('drive', 'v3', credentials=creds)
        logging.info("Google Drive service initialized successfully.")

    def list_files_in_folder(self, folder_id):
        """
        Lists all files within a specified folder.
        """
        if not folder_id:
            return []
        try:
            query = f"'{folder_id}' in parents and trashed=false"
            response = self.service.files().list(q=query,
                                                 spaces='drive',
                                                 fields='files(id, name, modifiedTime)').execute()
            return response.get('files', [])
        except Exception as e:
            logging.error(f"An error occurred listing files: {e}")
            return []

    def download_file(self, file_id, local_path, progress_callback=None):
        """
        Downloads a file from Drive and reports progress via an optional callback.
        """
        try:
            request = self.service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if progress_callback:
                    # Report the progress back to the UI
                    percent_complete = int(status.progress() * 100)
                    progress_callback(f"Downloading '{os.path.basename(local_path)}': {percent_complete}%")

            with open(local_path, 'wb') as f:
                f.write(fh.getvalue())
            
            if progress_callback:
                progress_callback(f"'{os.path.basename(local_path)}' complete.")
            
            logging.info(f"File downloaded successfully to {local_path}")
            return True
        except Exception as e:
            logging.error(f"An error occurred downloading file {file_id}: {e}")
            return False
    def upload_file(self, local_path, parent_folder_id):
        """
        Uploads a local file to the master folder. If it exists, it's updated.
        This is intended for admin use.
        """
        try:
            file_name = os.path.basename(local_path)
            logging.info(f"Uploading '{file_name}' to master folder...")
            query = f"name='{file_name}' and '{parent_folder_id}' in parents and trashed=false"
            response = self.service.files().list(q=query, fields='files(id)').execute()
            existing_files = response.get('files', [])
            
            media = MediaFileUpload(local_path, resumable=True)
            
            if existing_files:
                file_id = existing_files[0]['id']
                logging.info(f"File exists. Updating '{file_name}'...")
                self.service.files().update(fileId=file_id, media_body=media).execute()
            else:
                logging.info(f"File is new. Creating '{file_name}'...")
                file_metadata = {'name': file_name, 'parents': [parent_folder_id]}
                self.service.files().create(body=file_metadata, media_body=media).execute()
            
            logging.info(f"Successfully synced '{file_name}' to Drive.")
            return True
        except Exception as e:
            logging.error(f"An error occurred uploading file {local_path}: {e}")
            return False

    def delete_file_by_name(self, filename, parent_folder_id):
        """
        Deletes a file from the master folder.
        This is intended for admin use.
        """
        try:
            logging.info(f"Deleting '{filename}' from master folder...")
            query = f"name='{filename}' and '{parent_folder_id}' in parents and trashed=false"
            response = self.service.files().list(q=query, fields='files(id)').execute()
            files = response.get('files', [])

            if not files:
                logging.warning(f"File '{filename}' not found in Drive. No delete action taken.")
                return True

            file_id = files[0]['id']
            self.service.files().delete(fileId=file_id).execute()
            logging.info(f"Successfully deleted '{filename}' from Drive.")
            return True
        except Exception as e:
            logging.error(f"Failed to delete file '{filename}' from Drive: {e}")
            return False
