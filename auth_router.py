from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from google_auth_oauthlib.flow import Flow
from services.firestore_service import save_user_credentials, load_user_credentials
import os
from config import config

router = APIRouter()

def save_credentials(user_id, creds):
    """Credentialsオブジェクトを辞書に変換してFirestoreに保存"""
    save_user_credentials(user_id, creds)

def load_credentials(user_id):
    """Firestoreからデータを取得してCredentialsオブジェクトを再構築"""
    return load_user_credentials(user_id)

# 定数をconfig.pyから取得
CLIENT_SECRET_FILE = config.client_secret_file
SCOPES = config.scopes
REDIRECT_URI = config.redirect_uri

@router.get("/auth/google")
async def google_auth_start(user_id: str):
    # stateにuser_idを渡すことで、コールバック時に誰のトークンか識別する
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    auth_url, _ = flow.authorization_url(
        prompt='consent', # 常に同意画面を出してリフレッシュトークンを確実に取得
        access_type='offline',
        include_granted_scopes='true',
        state=user_id
    )
    return RedirectResponse(auth_url)

@router.get("/auth/google/callback")
async def google_auth_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")  # これがSlackのuser_id
    
    if not code or not state:
        return HTMLResponse("認証に失敗しました（パラメータ不足）", status_code=400)

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    
    # 認可コードをトークンに交換
    flow.fetch_token(code=code)
    credentials = flow.credentials
    
    # Firestoreに保存
    save_credentials(state, credentials)
    
    return HTMLResponse("<h3>Google認証が完了しました。Slackに戻って操作を再開してください。</h3>")