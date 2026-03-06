from typing import Dict
from google.cloud import firestore
from google.oauth2.credentials import Credentials
import hashlib

def save_user_credentials(user_id: str, creds: Credentials) -> None:
    """
    ユーザーのGoogle認証情報CredentialsオブジェクトをFirestoreに保存
    コレクション名: google_drive_tokens, ドキュメントID: user_id
    """
    db = firestore.Client()
    doc_ref = db.collection("google_drive_tokens").document(user_id)
    doc_ref.set({
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
        "expiry": creds.expiry.isoformat() if creds.expiry else None
    })

def load_user_credentials(user_id: str) -> Credentials | None:
    """
    FirestoreからユーザーのGoogle認証情報を取得しCredentialsを返す
    """
    db = firestore.Client()
    doc = db.collection("google_drive_tokens").document(user_id).get()
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

def save_folders_info_to_firestore(folders_info: Dict) -> None:
    """
    経理共有ドライブ配下の部署フォルダ情報をFirestoreに保存する（【経理作業用】などを除いた状態）
    コレクション名: folders_info, ドキュメントID: department_folders
    """
    db = firestore.Client()
    db.collection("folders_info").document("department_folders").set({"folders": folders_info})

def get_department_folders_from_firestore() -> Dict[str, str]:
    """
    Firestoreのfolders_info/department_foldersからフォルダ情報を取得し、
    drive_service.list_target_folders_under_parent()と同じ形式（{id: label}）の辞書を返す
    """
    db = firestore.Client()
    doc = db.collection("folders_info").document("department_folders").get()
    if not doc.exists:
        return {}
    data = doc.to_dict()
    folders = data.get("folders", {})
    # 形式変換（id: label）
    # 既に{フォルダID:ラベル}形式ならそのまま返す
    return dict(folders)

def get_department_accounting_users_from_firestore() -> list:
    """
    Firestoreから経理担当ユーザーリストを取得する
    Returns: list of user IDs
    """
    db = firestore.Client()
    doc = db.collection("settings").document("app_config").get()
    if not doc.exists:
        return []
    data = doc.to_dict()
    accounting_users = data.get("accounting_users", [])
    return accounting_users

def get_department_system_admin_members_from_firestore() -> list:
    """
    Firestoreからシステム管理者ユーザーリストを取得する
    Returns: list of user IDs
    """
    db = firestore.Client()
    doc = db.collection("settings").document("app_config").get()
    if not doc.exists:
        return []
    data = doc.to_dict()
    system_admin_members = data.get("system_admin_members", [])
    return system_admin_members

def get_google_drive_folder_id_from_firestore() -> str:
    """
    FirestoreからGoogle DriveのルートフォルダIDを取得する
    Returns: list of folder ID
    """
    db = firestore.Client()
    doc = db.collection("settings").document("app_config").get()
    if not doc.exists:
        return ""
    data = doc.to_dict()
    google_drive_folder_id = data.get("google_drive_folder_id", "")
    return google_drive_folder_id

def get_currencies_from_firestore() -> list:
    """
    Firestoreから通貨リストを取得する
    Returns: list of currency codes
    """
    db = firestore.Client()
    doc = db.collection("settings").document("app_config").get()
    if not doc.exists:
        return {}
    data = doc.to_dict()
    currencies = data.get("currencies", [])
    return currencies

def load_app_config_from_firestore() -> dict:
    """
    Firestoreのsettings/app_configドキュメントから設定情報を取得
    Returns: dict（redirect_uri, scopes など）
    """
    db = firestore.Client()
    doc_ref = db.collection("settings").document("app_config")
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict()
    else:
        print("Warning: Firestore config document not found.")
        return {}

def get_cached_dm_channel_id(user_ids: list) -> str | None:
    """
    ユーザーIDリストの組み合わせに対応する、保存済みのグループDM IDを取得する
    """
    if not user_ids:
        return None
        
    # ユーザーIDをソートして結合し、ハッシュ化（一意のキーを作成）
    user_key = hashlib.md5(",".join(sorted(user_ids)).encode()).hexdigest()
    
    db = firestore.Client()
    doc = db.collection("dm_channel_cache").document(user_key).get()
    
    if doc.exists:
        return doc.to_dict().get("channel_id")
    return None

def save_dm_channel_id_to_cache(user_ids: list, channel_id: str) -> None:
    """
    ユーザーIDリストの組み合わせと、作成されたグループDM IDをFirestoreに保存する
    """
    if not user_ids or not channel_id:
        return
        
    user_key = hashlib.md5(",".join(sorted(user_ids)).encode()).hexdigest()
    
    db = firestore.Client()
    db.collection("dm_channel_cache").document(user_key).set({
        "channel_id": channel_id,
        "members": sorted(user_ids), # デバッグ用にメンバー一覧も保存
        "updated_at": firestore.SERVER_TIMESTAMP
    })

def get_setup_message_blocks():
    """Firestore から設置用メッセージのブロック構成を取得する"""
    db = firestore.Client()
    try:
        doc_ref = db.collection("settings").document("invoice_setup_message")
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict().get("blocks", [])
        return None
    except Exception as e:
        print(f"Error fetching message from Firestore: {e}")
        return None