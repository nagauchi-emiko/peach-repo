"""
ファイルアップロード ハンドラー - Slack に PDF がアップロードされたときの処理
"""
from slack_bolt import App
from slack_sdk import WebClient
from services.drive_service import drive_service
from services.slack_service import slack_service
from services.firestore_service import get_department_accounting_users_from_firestore,load_user_credentials,get_google_drive_folder_id_from_firestore
from auth_router import get_google_auth_url
import urllib.request
import threading
import time
import re
import json
from datetime import datetime
from utility import accountant_only
from config import config

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
    
    def check_if_already_processed(client: WebClient, channel_id: str, thread_ts: str) -> bool:
        """
        スレッド内にBotによる完了メッセージが既に存在するか確認する
        """
        try:
            response = client.conversations_replies(channel=channel_id, ts=thread_ts, limit=20)
            messages = response.get("messages", [])

            for msg in messages:
                # メッセージの中に blocks があり、かつ特定のボタンIDが含まれているか
                blocks = msg.get("blocks", [])
                for block in blocks:
                    elements = block.get("elements", [])
                    for element in elements:
                        # 完了メッセージにのみ存在するボタンのIDをチェック
                        if element.get("action_id") in ["change_to_15th", "change_to_endofmonth"]:
                            return True
            return False
        except Exception as e:
            print(f"Error checking thread history: {e}")
            return False

    def extract_executor_id_from_message(message_data) -> str:
        """
        メッセージデータから「実行者」のメンション（ユーザーID）を抽出
        """
        if isinstance(message_data, list):
            message = message_data[0] if len(message_data) > 0 else {}
        else:
            message = message_data

        blocks = message.get('blocks', [])
        for block in blocks:
            if block.get('type') == 'section':
                text_content = block.get('text', {}).get('text', '')
                
                # `実行者` の後の改行にある <@U12345678> 形式を抽出
                pattern = r'`実行者`\n<@([A-Z0-9]+)>'
                match = re.search(pattern, text_content)
                
                if match:
                    return match.group(1) # ユーザーIDのみを返す
                    
        return "error"

    def extract_folderid_from_message(message_data) -> str:
        """
        メッセージデータ（リストまたは辞書）から部署フォルダIDを抽出
        """
        # message_data がリスト形式 [{}, {}] の場合、最初の要素を取り出す
        if isinstance(message_data, list):
            if len(message_data) > 0:
                message = message_data[0]
            else:
                return "error: empty list"
        else:
            message = message_data

        # messageの blocks 配列を取得
        blocks = message.get('blocks', [])
        
        # 各ブロックの中から「部署フォルダID」を探す
        for block in blocks:
            if block.get('type') == 'section':
                text_content = block.get('text', {}).get('text', '')
                
                # `部署フォルダID` の後の改行から、次の改行までの文字列を取得
                pattern = r'`部署フォルダID`\n([^\n]+)'
                match = re.search(pattern, text_content)
                
                if match:
                    # 抽出した文字列から余計な空白を削除して返す
                    return match.group(1).strip()
                    
        return "error"

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
        
        parent_message = message[0]
        blocks = parent_message.get('blocks', [])
        
        for block in blocks:
            # textフィールドを持つsectionを探す
            text_content = block.get('text', {}).get('text', '')
            
            # `保存ファイル名` の後の改行から、次の改行（または末尾）までを取得
            # 生のテキストを扱うので \n でマッチします
            pattern = r'`保存ファイル名`\n([^\n]+)'
            match = re.search(pattern, text_content)
            
            if match:
                file_name = match.group(1).strip()
                # 「格納日時」をタイムスタンプに置換
                file_name = file_name.replace('格納日時', now_str)
                return file_name

        # デフォルト名にタイムスタンプを付与
        return add_timestamp_to_filename(default_name, now_str)

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
            
            default_file_name = file_info.get("name", "document.pdf")
            
            # スレッド内にアップロードされた場合、親メッセージからファイル名と部署グループフォルダIDを取得
            if thread_ts:
                parent_message = get_thread_parent_message(client, channel_id, thread_ts)
                if parent_message:
                    # 実行者以外がアップロードした場合は、警告を出して終了
                    executor_id = extract_executor_id_from_message(parent_message)
                    print(f"抽出した実行者ID: {executor_id}")
                    if executor_id != user_id:
                        client.chat_postMessage(
                            channel=channel_id,
                            thread_ts=thread_ts,
                            text=f"⚠️ <@{user_id}>\nこの請求書登録の「実行者」は <@{executor_id}> さんです。実行者本人以外はファイルをアップロードできません。"
                        )
                        print(f"権限エラー: 実行者({executor_id}) != アップロード者({user_id})")
                        return
                    # 二重アップロードチェック
                    if check_if_already_processed(client, channel_id, thread_ts):
                        client.chat_postMessage(
                            channel=channel_id,
                            thread_ts=thread_ts,
                            text=f"⚠️ <@{user_id}>\nこのスレッドでは既にファイルの保存が完了しています。上書きや再アップロードはできません。"
                        )
                        print(f"スレッド {thread_ts} は既に処理済みのためスキップします。")
                        return
                    # PDF ファイルかチェック
                    if file_info.get("mimetype") != "application/pdf":
                        client.chat_postMessage(
                            channel=channel_id,
                            thread_ts=thread_ts,
                            text="⚠️ PDF ファイルのみアップロード可能です"
                        )
                        return
                    
                    file_name = extract_filename_from_message(parent_message, default_file_name)
                    print(f"スレッド親メッセージ: {parent_message}")
                    print(f"抽出したファイル名: {file_name}")
                    parent_folder_id = extract_folderid_from_message(parent_message)
                    print(f"抽出したフォルダID: {parent_folder_id}")

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

            credentials = load_user_credentials(user_id)
            if not credentials:
                # 認証用URLを生成
                auth_url = get_google_auth_url(user_id)
                client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text=(
                        f"⚠️ <@{user_id}> さん、Google Drive へのアクセス権限が確認できませんでした。\n"
                        f"<{auth_url}|こちらのリンクからGoogle認証> を完了してから、もう一度ファイルをアップロードしてください。"
                    )
                )
                print(f"Auth required for user {user_id}. Message sent to thread.")
                return
            drive_service.init(credentials)

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
            drive_folder_id = upload_result.get("target_folder_id", "")
            base_id = get_google_drive_folder_id_from_firestore()
            folder_path = drive_service.get_sub_folder_path(drive_folder_id, base_id)
            print(f"保存先: {folder_path}") 
            
            # 完了メッセージを送信
            slack_service.post_completion_message(
                channel_id=channel_id,
                thread_ts=thread_ts,
                file_name=file_name,
                folder_name=folder_path,
                folder_id=drive_folder_id,
                drive_url=drive_file_url,
                user_id=user_id
            )
            
        except Exception as e:
            print(f"Error handling file upload: {e}")
            import traceback
            traceback.print_exc()

    @app.action("change_to_15th", middleware=[accountant_only])
    def handle_change_to_15th(ack, body, client, action):
        ack()
        _handle_change_payment_date(
            client=client,
            body=body,
            action=action,
            new_payment="15日"
        )

    @app.action("change_to_endofmonth", middleware=[accountant_only])
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

        value_str = action.get("value")
        if value_str:
            try:
                # 文字列を辞書に変換
                value_data = json.loads(value_str)
                file_name = value_data.get("file_name")
                file_id = value_data.get("file_id")
                print(f"取得成功: {file_name}")
            except json.JSONDecodeError:
                print("JSONのデコードに失敗しました")
        print(f"action value: {action['value']}")

        # Google Driveのファイル名変更処理
        try:
            import re
            # 墨付きかっこ「【】」内の文字列をnew_paymentに置換
            new_file_name = re.sub(r'【[^】]*】', f'{new_payment}', file_name)

            # ユーザーごとのcredentialsをロード
            credentials = load_user_credentials(user_id)
            if not credentials:
                # 認証用URLを生成
                auth_url = get_google_auth_url(user_id)
                client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=message_ts,
                    text=(
                        f"⚠️ <@{user_id}> さん、Google Drive へのアクセス権限が確認できませんでした。\n"
                        f"<{auth_url}|こちらのリンクからGoogle認証> を完了してから、もう一度ファイル名変更ボタンを押してください。"
                    )
                )
                print(f"Auth required for user {user_id}. Message sent to thread.")
                return
            drive_service.init(credentials)
            drive_service.rename_file_by_id(file_id, new_file_name)
            drive_file_url = drive_service.get_file_url_by_id(file_id)

            # メンションする経理担当者IDを取得
            accounting_members = get_department_accounting_users_from_firestore()
            mentions = []
            if isinstance(accounting_members, list):
                mentions.extend([f"<@{uid}>" for uid in accounting_members])
            mention_text = " ".join(mentions)
            message = mention_text + "\n" + f"\n`ファイル名を変更しました`\n<{drive_file_url}|{new_file_name}>"

            # スレッドに完了通知
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=message_ts,
                text=message
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


