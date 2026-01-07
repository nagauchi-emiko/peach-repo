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
import re
import json

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
        for k, v in list(processed_events.items()):
            if now - v > ttl_seconds:
                processed_events.pop(k, None)

        if event_id in processed_events:
            return True

        processed_events[event_id] = now
        return False
    
    def get_thread_parent_message(
            client: WebClient,
            channel_id: str,
            thread_ts: str
            ) -> dict | None:
        """
        スレッドの先頭（親）メッセージを取得
        
        Args:
            client: Slack WebClient
            channel_id: チャンネルID
            thread_ts: スレッドのタイムスタンプ
            
        Returns:
            親メッセージの辞書、または None
        """
        try:
            # conversations.replies でスレッドのメッセージを取得
            # 最初のメッセージが親メッセージ
            response = client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                limit=1  # 親メッセージのみ取得
            )
            
            messages = response.get("messages", [])
            if messages:
                # return messages[0]
                return messages
            return None
            
        except Exception as e:
            print(f"Error fetching thread parent message: {e}")
            return None
    
    def extract_folderid_from_message(
            message,
            ) -> str:
        """
        メッセージテキストから部署フォルダIDを抽出
        
        Args:
            message: メッセージの辞書データ
            
        Returns:
            部署フォルダID
        """
        # 親メッセージを文字列に変換して正規表現で検索
        message_text = json.dumps(message, ensure_ascii=False)
        
        # パターン: *保存ファイル名*\n の後の値を取得
        pattern = r'\*部署フォルダID\*\\n([^"]+)'
        match = re.search(pattern, message_text)
        
        if match:
            safe_folderid = match.group(1)
            return safe_folderid
        return "error"  #★実装する

    def extract_filename_from_message(
            message,
            default_name: str = "document.pdf"
            ) -> str:
        """
        メッセージテキストからファイル名を抽出
        
        Args:
            message: メッセージの辞書データ
            default_name: ファイル名が取得できない場合のデフォルト値
            
        Returns:
            ファイル名（.pdf拡張子付き）
        """
        if not message:
            return default_name

        # 親メッセージを文字列に変換して正規表現で検索
        message_text = json.dumps(message, ensure_ascii=False)
        
        # パターン: *保存ファイル名*\n の後の値を取得
        pattern = r'\*保存ファイル名\*\\n([^"]+)'
        match = re.search(pattern, message_text)
        
        if match:
             # ファイル名として使えない文字を除去/置換
            # Windows/Mac/Linuxで使えない文字: \ / : * ? " < > |
            invalid_chars = r'[\\/:*?"<>|]'
            safe_filename = re.sub(invalid_chars, '_', match.group(1))
            return safe_filename
        return default_name


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

        print(f"handle_file_shared関数: {body['event']}")
        try:
            event = body["event"]
            file_id = event["file_id"]
            channel_id = event["channel_id"]
            user_id = event["user_id"]
            thread_ts = event.get("thread_ts")

            print(f"event : {event}")
            
            # ファイル情報を取得
            file_info_response = client.files_info(file=file_id)
            file_info = file_info_response["file"]

            # ファイル情報から親メッセージのタイムスタンプを取得
            thread_ts = file_info["shares"]["private"][channel_id][0]['thread_ts']

            print(f"thread_ts : {thread_ts}")
            
            # PDF ファイルかチェック
            if file_info.get("mimetype") != "application/pdf":
                client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text="⚠️ PDF ファイルのみアップロード可能です"
                )
                return
            
            # ========== ここが変更点 ==========
            # デフォルトはアップロードされたファイルの名前
            default_file_name = file_info.get("name", "document.pdf")
            
            # スレッド内にアップロードされた場合、親メッセージからファイル名とフォルダIDを取得
            if thread_ts:
                parent_message = get_thread_parent_message(client, channel_id, thread_ts)
                if parent_message:
                    file_name = extract_filename_from_message(parent_message, default_file_name)
                    print(f"スレッド親メッセージ: {parent_message}")
                    print(f"抽出したファイル名: {file_name}")
                    prent_folder_id = extract_folderid_from_message(parent_message)
                    print(f"抽出したファイル名: {prent_folder_id}")

                else:
                    file_name = default_file_name
                    print("親メッセージが取得できなかったため、デフォルトファイル名を使用")
            else:
                # スレッドでない場合はデフォルトのファイル名を使用
                file_name = default_file_name
                print("スレッド外のアップロードのため、デフォルトファイル名を使用")

            print(f"file_name: {file_name}")
            print(f"file_info: {file_info}")

            yyyymm = file_name.replace('【', '').replace('-', '')[:6]

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
                folder_name=yyyymm,
                parent_folder_id=prent_folder_id
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
    
    
