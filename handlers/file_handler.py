"""
ファイルアップロード ハンドラー - Slack に PDF がアップロードされたときの処理
"""
from slack_bolt import App
from slack_sdk import WebClient
from services.drive_service import drive_service
from services.slack_service import slack_service
import urllib.request
import threading
import time
import re
import json
from datetime import datetime
from utility import admin_only

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
        print(f"message_text: {message_text}")
        
        # パターン: `部署フォルダID`\n の後の値を取得
        # pattern = r'`部署フォルダID`\n([^"]+)'
        pattern = r'`部署フォルダID`[\n\s]+([^"\n]+)'
        match = re.search(pattern, message_text)
        
        if match:
            safe_folderid = match.group(1)
            return safe_folderid
        return "error"  #★実装する

    def extract_filename_from_message(
            message,
            default_name: str = "invoice.pdf"
            ) -> str:
        """
        メッセージテキストからファイル名を抽出
        
        Args:
            message: メッセージの辞書データ
            default_name: ファイル名が取得できない場合のデフォルト値
            
        Returns:
            ファイル名（.pdf拡張子付き）
        """
        now_str = datetime.now().strftime('%Y%m%d%H%M%S')
        # デフォルト名にタイムスタンプを付与
        if not message:
            return add_timestamp_to_filename(default_name, now_str)

        # 親メッセージを文字列に変換して正規表現で検索
        message_text = json.dumps(message, ensure_ascii=False)

        # パターン: `保存ファイル名`\n の後の値を取得
        pattern = r'`保存ファイル名`\n([^"]+)'
        match = re.search(pattern, message_text)
        
        if match:
            # ファイル名として使えない文字を除去/置換
            # Windows/Mac/Linuxで使えない文字: \ / : * ? " < > |
            invalid_chars = r'[\\/:*?"<>|]'
            safe_filename = re.sub(invalid_chars, '_', match.group(1))
            # 「格納日時」をタイムスタンプに置換
            safe_filename = safe_filename.replace('格納日時', now_str)
            return safe_filename
        # デフォルト名にタイムスタンプを付与
        return add_timestamp_to_filename(default_name, now_str)

    # @app.event("message")
    # def handle_file_upload(event, client: WebClient, ack):
    #     # 1. サブタイプ確認
    #     if event.get("subtype") != "file_share":
    #         ack()
    #         return

    #     # 2. 直接実行（スレッドは使わない！）
    #     try:
    #         # 必要なデータを event から抽出して process に渡すか、
    #         # process 関数自体を event 直接受取に書き換える
    #         body = {"event": event}
    #         process(body, client)
    #     except Exception as e:
    #         print(f"Error: {e}")
        
    #     # 3. 最後にACK
    #     ack()

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
            # # --- ここが message イベント用のキーになります ---
            # file_id = event["files"][0]["id"]      # event["file_id"] から変更
            # channel_id = event["channel"]          # event["channel_id"] から変更
            # user_id = event["user"]                # event["user_id"] から変更
            # # ----------------------------------------------

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
            
            # スレッド内にアップロードされた場合、親メッセージからファイル名と部署グループフォルダIDを取得
            if thread_ts:
                parent_message = get_thread_parent_message(client, channel_id, thread_ts)
                if parent_message:
                    file_name = extract_filename_from_message(parent_message, default_file_name)
                    print(f"スレッド親メッセージ: {parent_message}")
                    print(f"抽出したファイル名: {file_name}")
                    parent_folder_id = extract_folderid_from_message(parent_message)
                    print(f"抽出したファイル名: {parent_folder_id}")

                else:
                    file_name = default_file_name
                    print("親メッセージが取得できなかったため、デフォルトファイル名を使用")
            else:
                # スレッドでない場合はデフォルトのファイル名を使用
                file_name = default_file_name
                print("スレッド外のアップロードのため、デフォルトファイル名を使用")

            print(f"file_name: {file_name}")
            print(f"file_info: {file_info}")

            # 現在の年月を取得
            # （個別払い請求書は、支払希望日（支払期限）の日付にかかわらず、また、当月の〆有無にかかわらず、常に当月のフォルダに格納する）
            # （そもそも、個別払いは、「15日払い／月末払い」の格納に間に合わなかった場合に経理に直接依頼する目的のもの）
            yyyymm = datetime.now().strftime('%Y%m')

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
            
            # で当該年月の〆実施状況を取得


            # ユーザーごとのcredentialsをロード
            drive_service.init(user_id = user_id)

            # Google Drive にアップロード
            upload_result = drive_service.upload_pdf(
                file_content=file_content,
                file_name=file_name,
                yyyymm=yyyymm,
                parent_folder_id=parent_folder_id
            )
            
            if not upload_result:
                client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text="❌ Google Drive へのアップロードに失敗しました"
                )
                return
            
            drive_file_url = upload_result.get("webViewLink", "")
            
            # 完了メッセージを送信
            slack_service.post_completion_message(
                channel_id=channel_id,
                thread_ts=thread_ts,
                file_name=file_name,
                drive_url=drive_file_url,
                user_id=user_id
            )
            
        except Exception as e:
            print(f"Error handling file upload: {e}")
            import traceback
            traceback.print_exc()

    @app.action("change_to_15th", middleware=[admin_only])
    def handle_change_to_15th(ack, body, client, action):
        ack()
        _handle_change_payment_date(
            client=client,
            body=body,
            action=action,
            new_payment="15日"
        )

    @app.action("change_to_endofmonth", middleware=[admin_only])
    def handle_change_to_endofmonth(ack, body, client, action):
        ack()
        _handle_change_payment_date(
            client=client,
            body=body,
            action=action,
            new_payment="月末"
        )

    def _handle_change_payment_date(client, body, action, new_payment):
        """
        Google Driveのファイル名の一部を「15日」または「月末」に変更し、スレッドに通知
        """
        user_id = body["user"]["id"]
        channel_id = body["channel"]["id"]
        message_ts = body["message"]["ts"]
        file_name = action["value"]["file_name"]
        file_id = action["value"]["file_id"]

        print(f"action value: {action['value']}")

        # # SlackメッセージからファイルIDを取得
        # file_id = None
        # print(f"body: {body}")
        # try:
        #     blocks = body["message"].get("blocks", [])
        #     for block in blocks:
        #         if block.get("type") == "section" and block.get("text", {}).get("type") == "mrkdwn":
        #             text = block["text"]["text"]
        #             match = re.search(r'\*ファイルID\*: ([\w-]+)', text)
        #             if match:
        #                 file_id = match.group(1)
        #                 break
        # except Exception:
        #     pass

        # Google Driveのファイル名変更処理
        try:
            import re
            # 墨付きかっこ「【】」内の文字列をnew_paymentに置換
            new_file_name = re.sub(r'【[^】]*】', f'{new_payment}', file_name)

            # ユーザーごとのcredentialsをロード
            drive_service.init(user_id = user_id)
            drive_service.rename_file_by_id(file_id, new_file_name)

            # スレッドに完了通知
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,
                text=f"ファイルID: {file_id}\nファイル名を「{new_file_name}」に変更しました。"
            )
        except Exception as e:
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,
                text=f"ファイル名変更に失敗しました: {e}"
            )

def add_timestamp_to_filename(filename: str, now_str: str) -> str:
    base, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
    return f"{base}_{now_str}.{ext}" if ext else f"{base}_{now_str}"


