import os
import sys
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

class GoogleDriveUploader:
    def __init__(self, json_key_file_path, application_name="Google Drive API Uploader"):
        self.json_key_file_path = json_key_file_path
        self.application_name = application_name
        self.drive_service = None

    def initialize_drive_service(self):
        # Authenticate using the JSON key file
        credentials = service_account.Credentials.from_service_account_file(
            self.json_key_file_path, scopes=["https://www.googleapis.com/auth/drive.file"]
        )
        self.drive_service = build("drive", "v3", credentials=credentials)

    def search_item_by_name(self, item_name, folder_id=None, mime_type=None):
        query = "name = \"" + item_name + "\" and trashed = false"
        if folder_id:
            query += " and \"" + folder_id + "\" in parents"
        if mime_type:
            query += " and mimeType = \"" + mime_type + "\""

        results = self.drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get("files", [])
        return files[0] if files else None

    def delete_item(self, item_id):
        self.drive_service.files().delete(fileId=item_id).execute()
        print("Item with ID " + str(item_id) + " deleted.")

    def create_google_drive_folder(self, folder_name, parent_folder_id=None):
        # Search for an existing folder with the same name and reuse it if it exists
        existing_folder = self.search_item_by_name(folder_name, parent_folder_id, mime_type="application/vnd.google-apps.folder")
        if existing_folder:
            print("Using existing Google Drive folder: " + folder_name + " with ID: " + str(existing_folder["id"]))
            return existing_folder["id"]

        file_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_folder_id:
            file_metadata["parents"] = [parent_folder_id]

        folder = self.drive_service.files().create(body=file_metadata, fields="id").execute()
        print("Created new Google Drive folder: " + folder_name + " with ID: " + str(folder["id"]))
        return folder["id"]

    def upload_file(self, file_path, folder_id):
        file_name = os.path.basename(file_path)
        # Check if file already exists, if so, delete it to overwrite
        existing_file = self.search_item_by_name(file_name, folder_id)
        if existing_file:
            self.delete_item(existing_file["id"])

        file_metadata = {"name": file_name, "parents": [folder_id]}
        media = MediaFileUpload(file_path, resumable=True)

        uploaded_file = self.drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()
        print("File ID: " + str(uploaded_file["id"]) + " uploaded successfully.")

    def upload_directory_to_google_drive(self, local_directory_path, parent_folder_id):
        # Keep track of the mapping between local paths and Google Drive folder IDs
        folder_id_map = {local_directory_path: parent_folder_id}

        for root, dirs, files in os.walk(local_directory_path):
            # Get the parent folder ID for the current directory
            current_local_path = root
            current_folder_id = folder_id_map.get(current_local_path)

            # Create subdirectories in Google Drive
            for dir_name in dirs:
                local_subdir_path = os.path.join(current_local_path, dir_name)
                google_drive_folder_id = self.create_google_drive_folder(dir_name, current_folder_id)
                folder_id_map[local_subdir_path] = google_drive_folder_id

            # Upload files in the current directory
            for file_name in files:
                file_path = os.path.join(current_local_path, file_name)
                self.upload_file(file_path, current_folder_id)

    def upload_with_intermediate_folder(self, local_directory_path, google_drive_folder_id, intermediate_folder_name):
        # Create an intermediate folder and upload the directory contents under it
        intermediate_folder_id = self.create_google_drive_folder(intermediate_folder_name, google_drive_folder_id)
        self.upload_directory_to_google_drive(local_directory_path, intermediate_folder_id)

# Main function to accept command-line arguments
if __name__ == "__main__":
    json_key_file = sys.argv[1]
    local_directory = sys.argv[2]
    google_drive_folder_id = sys.argv[3]
    intermediate_folder = sys.argv[4]

    uploader = GoogleDriveUploader(json_key_file)
    uploader.initialize_drive_service()
    uploader.upload_with_intermediate_folder(local_directory, google_drive_folder_id, intermediate_folder)
