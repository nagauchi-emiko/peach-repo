import os
from typing import Optional, List, Dict, Any
from google.cloud import secretmanager
from google.cloud import firestore
from services.firestore_service import load_app_config_from_firestore

class Config:
    """アプリケーション設定クラス"""
    
    def __init__(self):
        # 0. まず環境を特定する（Cloud Run上なら K_SERVICE が必ず存在する）
        if os.environ.get("K_SERVICE"):
            self.environment = "production"
        else:
            self.environment = os.environ.get("ENVIRONMENT", "development")

        # 確定した環境をログに出す
        print(f"DEBUG: Current Environment is {self.environment}")

        # 1. 環境変数 (Platform/Infrastructure settings)
        self.environment = os.environ.get("ENVIRONMENT", "development")
        self.project_id = os.environ.get("GCP_PROJECT_ID", "sandbox-nagauchi")
        self.port = int(os.environ.get("PORT", 8080))

        # 初期化
        self.slack_bot_token = None
        self.slack_signing_secret = None
        self.redirect_uri = None
        self.scopes = []

        # 2. データの読み込み
        if self.environment == "production":
            # Cloud Run / Production 環境
            self._load_from_secret_manager()
            self._load_from_firestore()
        else:
            self._load_from_env_file()

    def _load_from_env_file(self):
        """ローカル開発環境用: .env ファイルから全て読み込み"""
        from dotenv import load_dotenv
        load_dotenv()
        
        # Secrets
        self.slack_bot_token = os.environ.get("SLACK_BOT_TOKEN")
        self.slack_signing_secret = os.environ.get("SLACK_SIGNING_SECRET")
        self.client_secret_file = os.environ.get("CLIENT_SECRET_FILE")
        
        # Firestore相当の設定もローカルでは .env から
        self.redirect_uri = os.environ.get("REDIRECT_URI")
        scopes_raw = os.environ.get("SCOPES")
        self.scopes = scopes_raw.split(",") if scopes_raw else []

    def _load_from_secret_manager(self):
        """Cloud Run環境用: Secret Manager から機密情報を取得"""
        self.slack_bot_token = self._get_secret("invoice-app-slack-bot-token")
        self.slack_signing_secret = self._get_secret("invoice-app-slack-signing-secret")
        # クライアントシークレットをファイルとしてマウントしている場合
        self.client_secret_file = "/etc/secrets/google/client_secret.json"

    def _load_from_firestore(self):
        """Cloud Run環境用: Firestore から動的設定を取得"""
        try:
            data = load_app_config_from_firestore()
            if data:
                self.redirect_uri = data.get("redirect_uri")
                self.scopes = data.get("scopes", [])
            else:
                print("Warning: Firestore config document not found.")
        except Exception as e:
            print(f"Error retrieving config from Firestore: {e}")

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