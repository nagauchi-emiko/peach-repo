# auth_router.py
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from google_auth_oauthlib.flow import Flow
import os
import pickle

router = APIRouter()

CLIENT_SECRET_FILE = "client_secret.json"
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets"
]
REDIRECT_URI = "https://your-domain/auth/google/callback"
TOKEN_DIR = "user_tokens"
os.makedirs(TOKEN_DIR, exist_ok=True)

def save_credentials(user_id, credentials):
    with open(os.path.join(TOKEN_DIR, f"{user_id}.pickle"), "wb") as f:
        pickle.dump(credentials, f)

def load_credentials(user_id):
    path = os.path.join(TOKEN_DIR, f"{user_id}.pickle")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return pickle.load(f)
    return None

@router.get("/auth/google")
async def google_auth_start(user_id: str):
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    auth_url, _ = flow.authorization_url(
        prompt='consent',
        access_type='offline',
        include_granted_scopes='true',
        state=user_id
    )
    return RedirectResponse(auth_url)

@router.get("/auth/google/callback")
async def google_auth_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")  # Slack user_id
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    flow.fetch_token(code=code)
    credentials = flow.credentials
    save_credentials(state, credentials)
    return HTMLResponse(f"<h2>Google認証が完了しました。Slackに戻って操作を再開してください。</h2>")