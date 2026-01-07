"""
設定ファイル - GCP Secret Managerから環境変数を取得
"""
import os
from typing import Optional
from google.cloud import secretmanager
import sys


class Config:
    """アプリケーション設定クラス"""
    
    def __init__(self):
        # 環境
        self.environment = os.environ.get("ENVIRONMENT", "development")
        # --- デバッグ用に追加 ---
        print(f"DEBUG: Current Environment is {self.environment}")
        print(f"DEBUG: Signing Secret exists: {bool(os.environ.get('SLACK_SIGNING_SECRET'))}")
        # ----------------------
        self.project_id = os.environ.get("GCP_PROJECT_ID", "sandbox-nagauchi")
        self.port = int(os.environ.get("PORT", 8080))

        self.google_drive_folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
        self.admin_group_members = os.environ.get("ADMIN_GROUP_MEMBERS", "").split(",")
        
        # ローカル開発環境では .env ファイルから読み込み
        if self.environment == "development":
            self._load_from_env_file()
        else:
            # Cloud Run 環境では Secret Manager から読み込み
            self._load_from_secret_manager()
    
    def _load_from_env_file(self):
        """ローカル開発環境用: .env ファイルから読み込み"""
        from dotenv import load_dotenv
        load_dotenv()
        
        self.slack_bot_token = os.environ.get("SLACK_BOT_TOKEN")
        self.slack_signing_secret = os.environ.get("SLACK_SIGNING_SECRET")
        # self.google_service_account_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") 要らないかも★

        # auth_router.py用定数
        self.client_secret_file = os.environ.get("CLIENT_SECRET_FILE")
        self.redirect_uri = os.environ.get("REDIRECT_URI")
        # self.token_dir = os.environ.get("TOKEN_DIR") 要らないかも★
        scopes_raw = os.environ.get("SCOPES")
        self.scopes = scopes_raw.split(",") if scopes_raw else []
    
    def _load_from_secret_manager(self):
        """Cloud Run環境用: Secret Manager から読み込み"""
        self.slack_bot_token = self._get_secret("SLACK_BOT_TOKEN")
        self.slack_signing_secret = self._get_secret("SLACK_SIGNING_SECRET")
        # self.google_service_account_json = self._get_secret("google-service-account-json") 要らないかも★
        
        # auth_router.py用定数
        self.client_secret_file = "/secrets/client_secret.json"
        self.redirect_uri = self._get_secret("REDIRECT_URI")
        # self.token_dir = self._get_secret("TOKEN_DIR") 要らないかも★
        scopes_raw = self._get_secret("SCOPES")
        self.scopes = scopes_raw.split(",") if scopes_raw else []
    
    def _get_secret(self, secret_id: str) -> Optional[str]:
        """Secret Manager からシークレットを取得"""
        try:
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{self.project_id}/secrets/{secret_id}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8")
        except Exception as e:
            print(f"Error retrieving secret {secret_id}: {e}")
            return None


# グローバルインスタンス
config = Config()
