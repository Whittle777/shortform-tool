import os
import glob
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def get_authenticated_service(logger=None):
    """
    Looks for a client_secret*.json file, authenticates with YouTube, and returns an API client.
    Saves and reuses token.json.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                if logger: logger(f"Failed to refresh token: {e}")
                creds = None
        
        if not creds:
            # Find client_secret JSON file dynamically
            client_secrets = glob.glob('client_secret_*.json')
            if not client_secrets:
                 raise FileNotFoundError("Could not find client_secret file. Please download it from Google Cloud Console.")
                 
            client_secret_file = client_secrets[0]
            if logger: logger(f"Authenticating using {client_secret_file}...")
            
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
            # Run local server to capture the auth code
            creds = flow.run_local_server(port=0)
            
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
    return build('youtube', 'v3', credentials=creds)

def initialize_youtube_auth(logger=None):
    """
    Wrapper around get_authenticated_service to ensure token.json is generated at startup.
    """
    try:
        get_authenticated_service(logger=logger)
        if logger: logger("YouTube Auth initialized successfully.")
        return True
    except Exception as e:
        if logger: logger(f"Error initializing YouTube Auth: {e}")
        return False

def upload_video_to_youtube(video_path, caption, tags=None, logger=None):
    """
    Uploads a video to YouTube using the authenticated API.
    """
    if tags is None:
        tags = ["shorts", "facts", "interesting", "foryou"]
        
    try:
        if logger: logger(f"Starting YouTube upload for: {video_path}")
        youtube = get_authenticated_service(logger=logger)
        
        # YouTube requires a title of max 100 characters. We'll use the beginning of the caption.
        title = caption.split('\n')[0][:100].strip()
        if not title:
            title = "Fascinating Facts!"
            
        # Describe the video and snippet
        body = {
            'snippet': {
                'title': title,
                'description': caption,
                'tags': tags,
                'categoryId': '24' # Entertainment
            },
            'status': {
                'privacyStatus': 'public',  # public, private, or unlisted
                'selfDeclaredMadeForKids': False
            }
        }

        # Call the API's videos.insert method to create and upload the video.
        insert_request = youtube.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True)
        )
        
        response = insert_request.execute()
        if logger: logger(f"Upload Successful! Video ID: {response.get('id')}")
        
    except Exception as e:
        if logger: logger(f"Failed to upload to YouTube: {e}")
        print(f"Failed to upload to YouTube: {e}")
