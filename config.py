"""
設定ファイル - GCP Secret Managerから環境変数を取得
"""
import os
from typing import Optional
from google.cloud import secretmanager


class Config:
    """アプリケーション設定クラス"""
    
    def __init__(self):
        # 環境
        self.environment = os.environ.get("ENVIRONMENT", "development")
        self.project_id = os.environ.get("GCP_PROJECT_ID", "sandbox-nagauchi")
        self.port = int(os.environ.get("PORT", 8080))
        
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
        self.google_service_account_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        self.management_spreadsheet_id = os.environ.get("MANAGEMENT_SPREADSHEET_ID")
        self.google_drive_folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
        self.admin_group_members = os.environ.get("ADMIN_GROUP_MEMBERS", "").split(",")
    
    def _load_from_secret_manager(self):
        """Cloud Run環境用: Secret Manager から読み込み"""
        self.slack_bot_token = self._get_secret("slack-bot-token")
        self.slack_signing_secret = self._get_secret("slack-signing-secret")
        self.google_service_account_json = self._get_secret("google-service-account-json")
        self.management_spreadsheet_id = self._get_secret("management-spreadsheet-id")
        self.google_drive_folder_id = self._get_secret("google-drive-folder-id")
        admin_members = self._get_secret("admin-group-members")
        self.admin_group_members = admin_members.split(",") if admin_members else []
    
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
