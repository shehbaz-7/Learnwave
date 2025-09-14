

import os
import sys
import logging
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Define the scope of access needed.
SCOPES = ['https://www.googleapis.com/auth/drive']

# --- PATHING FIX ---
# This function correctly finds bundled files in both script and .exe mode.
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # If not running as a PyInstaller bundle, use the normal script path
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# Define the paths for our key files using the new robust logic.
CREDENTIALS_PATH = resource_path('credentials.json')
# The user's token should ALWAYS be in their permanent AppData folder, not a temporary one.
APP_DATA_DIR = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Learnwave")
TOKEN_PATH = os.path.join(APP_DATA_DIR, 'token.json')
# --- END PATHING FIX ---

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def authenticate_google():
    """
    Handles the user authentication flow for Google Drive.
    - Checks for an existing, valid token in the AppData folder.
    - If not found or expired, it initiates the OAuth 2.0 flow using the bundled credentials.json.
    - The resulting token is saved for future runs in the AppData folder.
    
    Returns:
        google.oauth2.credentials.Credentials: The authenticated credentials object.
    """
    creds = None
    os.makedirs(APP_DATA_DIR, exist_ok=True) # Ensure AppData folder exists

    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
            logging.info(f"Loaded credentials from {TOKEN_PATH}.")
        except Exception as e:
            logging.error(f"Failed to load credentials from token: {e}")
            creds = None

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                logging.info("Credentials expired. Refreshing token...")
                creds.refresh(Request())
            except Exception as e:
                logging.error(f"Failed to refresh token: {e}. Re-authentication is required.")
                creds = None
        else:
            logging.info("No valid credentials found. Starting authentication flow...")
            if not os.path.exists(CREDENTIALS_PATH):
                logging.error(f"FATAL: credentials.json not found at {CREDENTIALS_PATH}. The application build is broken.")
                # In a real app, this would be a GUI error.
                return None
                
            try:
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
                creds = flow.run_local_server(port=0)
            except Exception as e:
                logging.error(f"Failed to run authentication flow: {e}")
                return None

        # Save the credentials for the next run
        if creds:
            try:
                with open(TOKEN_PATH, 'w') as token_file:
                    token_file.write(creds.to_json())
                logging.info(f"Credentials saved to {TOKEN_PATH}")
            except Exception as e:
                logging.error(f"Failed to save token: {e}")

    return creds

if __name__ == '__main__':
    # This is a simple test to verify that authentication works.
    print("Attempting to authenticate...")
    credentials = authenticate_google()
    if credentials:
        print("\nAuthentication Successful!")
        print(f"Token is valid. Ready to make API calls on behalf of the user.")
        print(f"(Token will be stored in: {TOKEN_PATH})")
    else:
        print("\nAuthentication Failed. Please check the console for errors.")
