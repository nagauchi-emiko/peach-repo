"""
ファイルアップロード ハンドラー - Slack に PDF がアップロードされたときの処理
"""
from slack_bolt import App
from slack_sdk import WebClient
from services.drive_service import drive_service
from services.slack_service import slack_service
from services.sheets_service import sheets_service
import urllib.request
import threading
import time


def register_file_handlers(app: App) -> None:
    """
    ファイルアップロード ハンドラーを登録
    
    Args:
        app: Slack Bolt アプリケーション
    """

    # 簡易的な「処理済みイベントID」の保存場所（プロセスが落ちると消える）
    # 本番は DB などを推奨
    processed_events = {}

    def is_event_processed(event_id: str, ttl_seconds: int = 60 * 60) -> bool:
        """event_id がすでに処理済みかどうかを判定"""
        now = time.time()
        # 古いものを軽く掃除
        for k, v in list(processed_events.items()):
            if now - v > ttl_seconds:
                processed_events.pop(k, None)

        if event_id in processed_events:
            return True

        processed_events[event_id] = now
        return False
    
    @app.event("file_shared")
    def handle_file_shared(body, client: WebClient, ack):
        """
        Slack にファイルがアップロードされたときの処理
        """
         # まず即座に ACK を返す（Slack への 200 OK）
        ack()

        # バックグラウンドで処理させる
        thread = threading.Thread(
            target=process,
            args=(body, client)
            )
        thread.start()

    # 以降の重い処理は別スレッドで実行するなどして、
    # ACK のレスポンス時間に影響しないようにする
    def process(body, client: WebClient):
        event_id = body.get("event_id")

        # ---- ここで二重実行を防ぐ ----
        if event_id and is_event_processed(event_id):
            print(f"Duplicate event {event_id} skipped")
            return
        # --------------------------------

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
            
            # ユーザーごとのcredentialsをロード
            drive_service.init(user_id = user_id)

            # Google Drive にアップロード
            upload_result = drive_service.upload_pdf(
                file_content=file_content,
                file_name=file_name,
                folder_name="格納フォルダ１"
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
    
    
