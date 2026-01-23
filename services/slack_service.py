"""
Slack サービス - DM グループ作成、メッセージ送信、ファイル操作
"""
from typing import List, Dict, Optional
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from config import config


class SlackService:
    """Slack 連携クラス"""
    
    def __init__(self):
        """初期化"""
        self.client = WebClient(token=config.slack_bot_token)
    
    def create_group_dm(self, user_ids: List[str]) -> Optional[str]:
        """
        複数ユーザーとのグループ DM（プライベートチャンネル）を作成
        
        Args:
            user_ids: ユーザーID のリスト
        
        Returns:
            チャンネル ID（DM のチャンネルID）
        """
        try:
            # group_dm の場合は conversations.open を使用（複数人）
            response = self.client.conversations_open(
                users=user_ids,
                is_group=True
            )
            return response['channel']['id']
        except SlackApiError as e:
            print(f"Error creating group DM: {e.response['error']}")
            return None
    
    def post_invoice_message(
        self,
        channel_id: str,
        invoice_data: Dict,
        user_id: str
    ) -> Optional[str]:
        """
        請求書情報をメッセージとして DM チャンネルに送信
        
        Args:
            channel_id: チャンネル ID
            invoice_data: 請求書データ
            user_id: 実行ユーザーの ID
        
        Returns:
            メッセージの タイムスタンプ（ts）
        """
        
        """
        保存PDFファイル名規則
            【yyyymm期限】_[社名]_[部門]_[金額]_[仕入れか販管費か]_[経理への連絡]_[アップロードyyyymmddhhmmss].pdf
        """
        try:
            # ブロックを構築
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "📋 請求書登録確認  ※開発中のアプリのテストです！※"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*実行ユーザー*\n<@{user_id}>"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*実行日時*\n{invoice_data.get('timestamp', '未設定')}"
                        }
                    ]
                },
                {
                    "type": "divider"
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*保存先フォルダ*\n{invoice_data.get('folder', '未設定')}/{invoice_data.get('deadline', '未設定').replace('-','')[:6]}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*部署フォルダID*\n{invoice_data.get('folder_id', '未設定')}"
                        }
                    ]
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*支払先企業名*\n{invoice_data.get('company', '未設定')}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*経費区分*\n{invoice_data.get('expense_type', '未設定')}"
                        }
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*支払希望日*\n{invoice_data.get('deadline', '未設定')}"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*通貨*\n{invoice_data.get('currency', '日本円')}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*請求金額*\n{invoice_data.get('amount', '0')}"
                        }
                    ]
                },
                {
                    "type": "section",
                    "text": {
                            "type": "mrkdwn",
                            "text": f"*連絡事項*\n{invoice_data.get('notes', 'なし')}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                            "type": "mrkdwn",
                            "text": f"*保存ファイル名*\n【{invoice_data.get('deadline')}期限】_{invoice_data.get('company')}_{invoice_data.get('folder')}_{invoice_data.get('amount')}_{invoice_data.get('notes')}_格納日時.pdf"
                    }
                },
                {
                    "type": "divider"
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "📎 *このスレッドに PDF ファイルをアップロードしてください*\n\nアップロードされたファイルは自動的に Google Drive に保存されます。"
                    }
                }
            ]
            
            response = self.client.chat_postMessage(
                channel=channel_id,
                blocks=blocks,
                text="請求書登録確認"
                # text="請求書登録確認",
                # metadata={
                #     "event_type": "pdf_processing_task",
                #     "event_payload": {
                #         "hidden_folder_id": invoice_data.get('folder_id', '未設定') 
                #     }
                # }
            )
            
            return response['ts']
        except SlackApiError as e:
            print(f"Error posting invoice message: {e.response['error']}")
            return None
    
    def post_completion_message(
        self,
        channel_id: str,
        thread_ts: str,
        file_name: str,
        drive_url: str
    ) -> bool:
        """
        PDF アップロード完了メッセージをスレッドに送信
        
        Args:
            channel_id: チャンネル ID
            thread_ts: スレッドのタイムスタンプ
            file_name: ファイル名
            drive_url: Google Drive の URL
        
        Returns:
            成功時は True、失敗時は False
        """
        try:
            message = (
                f"✅ PDF ファイルがアップロードされました\n\n"
                f"*ファイル名*: {file_name}\n"
                f"*保存先*: <{drive_url}|Google Drive で確認>"
            )
            
            self.client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=message,
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": message
                        }
                    }
                ]
            )
            
            return True
        except SlackApiError as e:
            print(f"Error posting completion message: {e.response['error']}")
            return False
    
    def get_file_url(self, file_id: str) -> Optional[str]:
        """
        Slack にアップロードされたファイルの URL を取得
        
        Args:
            file_id: ファイルID
        
        Returns:
            ダウンロード URL
        """
        try:
            response = self.client.files_info(file=file_id)
            file_info = response['file']
            return file_info.get('url_private_download')
        except SlackApiError as e:
            print(f"Error getting file URL: {e.response['error']}")
            return None
    
    def get_user_info(self, user_id: str) -> Optional[Dict]:
        """
        ユーザー情報を取得
        
        Args:
            user_id: ユーザーID
        
        Returns:
            ユーザー情報
        """
        try:
            response = self.client.users_info(user=user_id)
            user = response['user']
            return {
                'id': user['id'],
                'name': user['name'],
                'real_name': user.get('real_name', user['name']),
                'email': user.get('profile', {}).get('email', '')
            }
        except SlackApiError as e:
            print(f"Error getting user info: {e.response['error']}")
            return None


# グローバルインスタンス
slack_service = SlackService()
