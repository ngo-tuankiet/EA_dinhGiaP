import logging
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from valuation.config import settings

logger = logging.getLogger(__name__)

def upload_report_to_drive(file_path: str, mime_type: str = None) -> dict:
    """
    Upload a single file to Google Drive using the service account credentials.
    """
    if not settings.google_service_account_json or not settings.google_drive_folder_id:
        logger.warning("Google Drive config missing. Skipping upload.")
        return {"status": "skipped", "reason": "Missing GDrive config"}
    
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return {"status": "error", "reason": "File not found"}

    try:
        # Authenticate
        creds = service_account.Credentials.from_service_account_file(
            settings.google_service_account_json,
            scopes=['https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/drive']
        )
        service = build('drive', 'v3', credentials=creds)

        filename = os.path.basename(file_path)

        # File metadata
        file_metadata = {
            'name': filename,
            'parents': [settings.google_drive_folder_id]
        }
        
        # Determine mime_type if not provided
        if not mime_type:
            if filename.endswith(".pdf"):
                mime_type = 'application/pdf'
            elif filename.endswith(".docx"):
                mime_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            else:
                mime_type = 'application/octet-stream'

        # Upload media
        media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()

        logger.info(f"Successfully uploaded {filename} to Google Drive. File ID: {file.get('id')}")
        return {"status": "success", "file_id": file.get('id')}

    except Exception as e:
        logger.error(f"Failed to upload to Google Drive: {e}")
        return {"status": "error", "error": str(e)}
