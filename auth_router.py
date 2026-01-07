# auth_router.py

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from google_auth_oauthlib.flow import Flow
from google.cloud import firestore  # 追加
from google.oauth2.credentials import Credentials
import os
from config import config

router = APIRouter()

# Firestoreクライアントの初期化
db = firestore.Client()
COLLECTION_NAME = "google_drive_tokens"

# 定数をconfig.pyから取得
CLIENT_SECRET_FILE = config.client_secret_file
SCOPES = config.scopes
REDIRECT_URI = config.redirect_uri

def save_credentials(user_id, creds):
    """Credentialsオブジェクトを辞書に変換してFirestoreに保存"""
    doc_ref = db.collection(COLLECTION_NAME).document(user_id)
    doc_ref.set({
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
        "expiry": creds.expiry.isoformat() if creds.expiry else None
    })

def load_credentials(user_id):
    """Firestoreからデータを取得してCredentialsオブジェクトを再構築"""
    doc = db.collection(COLLECTION_NAME).document(user_id).get()
    if not doc.exists:
        return None
    
    data = doc.to_dict()
    return Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes")
    )

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

# # auth_router.py

# from fastapi import APIRouter, Request
# from fastapi.responses import RedirectResponse, HTMLResponse
# from google_auth_oauthlib.flow import Flow
# import os
# import pickle
# from config import config

# router = APIRouter()

# # 定数をconfig.pyから取得
# CLIENT_SECRET_FILE = config.client_secret_file
# SCOPES = config.scopes
# REDIRECT_URI = config.redirect_uri
# TOKEN_DIR = config.token_dir
# os.makedirs(TOKEN_DIR, exist_ok=True)

# def save_credentials(user_id, credentials):
#     with open(os.path.join(TOKEN_DIR, f"{user_id}.pickle"), "wb") as f:
#         pickle.dump(credentials, f)

# def load_credentials(user_id):
#     path = os.path.join(TOKEN_DIR, f"{user_id}.pickle")
#     if os.path.exists(path):
#         with open(path, "rb") as f:
#             return pickle.load(f)
#     return None

# @router.get("/auth/google")
# async def google_auth_start(user_id: str):
#     flow = Flow.from_client_secrets_file(
#         CLIENT_SECRET_FILE,
#         scopes=SCOPES,
#         redirect_uri=REDIRECT_URI
#     )
#     auth_url, _ = flow.authorization_url(
#         prompt='consent',
#         access_type='offline',
#         include_granted_scopes='true',
#         state=user_id
#     )
#     return RedirectResponse(auth_url)

# @router.get("/auth/google/callback")
# async def google_auth_callback(request: Request):
#     code = request.query_params.get("code")
#     state = request.query_params.get("state")  # Slack user_id
#     flow = Flow.from_client_secrets_file(
#         CLIENT_SECRET_FILE,
#         scopes=SCOPES,
#         redirect_uri=REDIRECT_URI
#     )
#     flow.fetch_token(code=code)
#     credentials = flow.credentials
#     save_credentials(state, credentials)
#     return HTMLResponse(f"<h3>Google認証が完了しました。Slackに戻って操作を再開してください。</h3>")