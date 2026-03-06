"""
Slack サービス - DM グループ作成、メッセージ送信、ファイル操作
"""
from typing import List, Dict, Optional
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from config import config
import json
from services.firestore_service import get_department_accounting_users_from_firestore,get_cached_dm_channel_id,save_dm_channel_id_to_cache
import re

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
            cached_channel_id = get_cached_dm_channel_id(user_ids)
            if cached_channel_id:
                return cached_channel_id
            # group_dm の場合は conversations.open を使用（複数人）
            response = self.client.conversations_open(
                users=user_ids,
                is_group=True
            )
            # キャッシュに保存
            save_dm_channel_id_to_cache(user_ids, response['channel']['id'])
            return response['channel']['id']
        except SlackApiError as e:
            print(f"Error creating group DM: {e.response['error']}")
            return None
    
    def post_invoice_message(
        self,
        channel_id: str,
        invoice_data: Dict,
        user_id: str,
        accounting_users: List[str]
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
            accounting_users_mention_txt = " ".join([f"<@{uid}>" for uid in accounting_users]) if isinstance(accounting_users, list) else ""
            invoice_details = (
                # f"*請求書アップロード*\n\n"
                f"`実行者`\n<@{user_id}> ({accounting_users_mention_txt})"
                f"\n*スレッドに PDF ファイルを添付して投稿してください*\n※ファイルは自動的に Google Drive に保存されます（処理完了まで数十秒かかります）\n\n"
                f"`保存先フォルダ`\n{invoice_data.get('folder', '未設定')}/{invoice_data.get('deadline', '未設定').replace('-', '')[:6]}\n"
                f"`保存ファイル名`\n【{invoice_data.get('deadline')}期限】_{invoice_data.get('company')}_{invoice_data.get('folder')}_{invoice_data.get('currency', '日本円')}{invoice_data.get('amount')}_{invoice_data.get('notes')}_格納日時.pdf\n"
                f"`支払先企業名`\n{invoice_data.get('company', '未設定')}\n"
                f"`費用種別`\n{invoice_data.get('expense_type', '未設定')}\n"
                f"`支払希望日`\n{invoice_data.get('deadline', '未設定')}\n"
                f"`通貨`\n{invoice_data.get('currency', '日本円')}\n"
                f"`請求金額`\n{invoice_data.get('amount', '0')}\n"
                f"`連絡事項`\n{invoice_data.get('notes', 'なし')}\n"
                f"`部署フォルダID`\n{invoice_data.get('folder_id', '未設定')}\n"
            )

            blocks = [
                # {
                #     "type": "section",
                #     "text": {
                #         "type": "mrkdwn",
                #         "text": "📎*スレッドに PDF ファイルを添付して投稿してください*\n※アップロードされたファイルは自動的に Google Drive に保存されます\n（処理完了まで数十秒かかります）"
                #     }
                # },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": invoice_details
                    }
                }
            ]
            
            response = self.client.chat_postMessage(
                channel=channel_id,
                blocks=blocks,
                text="PDFをアップロードしてください"
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
        folder_name: str,
        folder_id: str,
        drive_url: str,
        user_id: str
    ) -> bool:
        """
        PDF アップロード完了メッセージをスレッドに送信（経理担当者用ボタン付き）
        """
        try:
            message = (
                f"✅ *PDF ファイルがアップロードされました*\n\n"
                f"*フォルダ：*<https://drive.google.com/drive/folders/{folder_id}|{folder_name}>\n"
                f"*ファイル名：*<{drive_url}|{file_name}>"
            )
            # メンションのリストを作成（実行者 + 経理担当者）
            accounting_members = get_department_accounting_users_from_firestore()
            mentions = [f"<@{user_id}>"]
            if isinstance(accounting_members, list):
                mentions.extend([f"<@{uid}>" for uid in accounting_members])
            mention_text = " ".join(mentions)

            message = mention_text + "\n" + message

            # drive_urlからファイルIDを抽出
            file_id = None
            match = re.search(r'/d/([\w-]+)', drive_url)
            if match:
                file_id = match.group(1)
            else:
                # 旧形式URLの場合
                match2 = re.search(r'id=([\w-]+)', drive_url)
                if match2:
                    file_id = match2.group(1)
            payload_data = {
                "file_id": file_id if file_id else "none",
                "file_name": file_name
            }
            # 文字列に変換
            button_value_str = json.dumps(payload_data)

            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": message
                    }
                },
                {
                    "type": "actions",
                    "block_id": "admin_actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "15日払いに変更（経理専用）"},
                            "action_id": "change_to_15th",
                            "style": "primary",
                            "value": button_value_str
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "月末払いに変更（経理専用）"},
                            "action_id": "change_to_endofmonth",
                            "style": "primary",
                            "value": button_value_str
                        }
                    ]
                }
            ]
            print(f"post_completion_message blocks: {blocks}")
            self.client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=message,
                blocks=blocks
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
    
    def update_to_auth_required_modal(self, client, view_id: str, user_id: str):
        """
        指定されたモーダルを認証要求画面に更新する
        """
        from auth_router import get_google_auth_url
        
        auth_url = get_google_auth_url(user_id)
        view = self._create_auth_required_modal(auth_url) 
        
        return client.views_update(view_id=view_id, view=view)
    
    def _create_auth_required_modal(self, auth_url: str) -> Dict:
        """
        認証が必要な場合のモーダルを構築
        """
        return {
            "type": "modal",
            "callback_id": "invoice_modal_auth",
            "title": {
                "type": "plain_text",
                "text": "認証が必要です"
            },
            "close": {
                "type": "plain_text",
                "text": "閉じる"
            },
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": ":warning: *Google認証が必要です*\n\n請求書登録機能を使用するには、Google認証を完了してください。"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"<{auth_url}|:key: こちらをクリックして認証>"
                    }
                }
            ]
        }


# グローバルインスタンス
slack_service = SlackService()
