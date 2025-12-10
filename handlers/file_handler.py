"""
ファイルアップロード ハンドラー - Slack に PDF がアップロードされたときの処理
"""
from slack_bolt import App
from slack_sdk import WebClient
from services.drive_service import drive_service
from services.slack_service import slack_service
from services.sheets_service import sheets_service
import urllib.request


def register_file_handlers(app: App) -> None:
    """
    ファイルアップロード ハンドラーを登録
    
    Args:
        app: Slack Bolt アプリケーション
    """
    
    @app.event("file_shared")
    def handle_file_shared(body, client: WebClient):
        """
        Slack にファイルがアップロードされたときの処理
        """
        print(f"handle_file_shared関数: {body["event"]}")
        try:
            event = body["event"]
            file_id = event["file_id"]
            channel_id = event["channel_id"]
            user_id = event["user_id"]
            thread_ts = event.get("thread_ts")
            
            # ファイル情報を取得
            file_info_response = client.files_info(file=file_id)
            file_info = file_info_response["file"]
            
            # PDF ファイルかチェック
            if file_info.get("mimetype") != "application/pdf":
                client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text="⚠️ PDF ファイルのみアップロード可能です"
                )
                return
            
            file_name = file_info.get("name", "document.pdf")

            print(f"file_name: {file_name}")
            print(f"file_info: {file_info}")

            # ファイルをダウンロード
            download_url = file_info.get("url_private_download")
            if not download_url:
                client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text="❌ ファイルのダウンロードに失敗しました"
                )
                return
            
            # Slack API トークンをヘッダーに含めてダウンロード
            headers = {"Authorization": f"Bearer {client.token}"}
            request = urllib.request.Request(download_url, headers=headers)
            
            try:
                with urllib.request.urlopen(request) as response:
                    file_content = response.read()
            except Exception as e:
                print(f"Error downloading file: {e}")
                client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text="❌ ファイルのダウンロードに失敗しました"
                )
                return
            
            # Google Drive にアップロード
            upload_result = drive_service.upload_pdf(
                file_content=file_content,
                file_name=file_name,
                folder_name="請求書"
            )
            
            if not upload_result:
                client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text="❌ Google Drive へのアップロードに失敗しました"
                )
                return
            
            drive_file_url = upload_result.get("webViewLink", "")
            
            # スプレッドシートのステータスを更新
            sheets_service.update_invoice_status(
                status="completed",
                drive_file_url=drive_file_url
            )
            
            # 完了メッセージを送信
            slack_service.post_completion_message(
                channel_id=channel_id,
                thread_ts=thread_ts,
                file_name=file_name,
                drive_url=drive_file_url
            )
            
        except Exception as e:
            print(f"Error handling file upload: {e}")
            import traceback
            traceback.print_exc()
