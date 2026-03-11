"""
スラッシュコマンド ハンドラー
"""
from typing import Optional, List, Dict
from datetime import datetime
from slack_bolt import App
from services.drive_service import drive_service
from services.firestore_service import get_department_folders_from_firestore
from services.slack_service import slack_service
from services.firestore_service import save_folders_info_to_firestore, get_department_accounting_users_from_firestore,get_department_system_admin_members_from_firestore,get_currencies_from_firestore,load_user_credentials,get_setup_message_blocks
from utility import accountant_only


def register_command_handlers(app: App) -> None:

    app.command("/update_folders_info", middleware=[accountant_only])(
        ack=handle_update_folders_info_ack,
        lazy=[handle_update_folders_info_lazy]
    )

    @app.command("/setup_invoice_button")
    def setup_invoice_button(ack, say, command):
        ack()
        blocks = get_setup_message_blocks()
        if not blocks:
            print("Warning: Using default blocks as Firestore config was not found.")
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*個別払請求書の登録はこちらから*"
                    }
                },
                {
                    "type": "rich_text",
                    "elements": [
                        # 1〜2番のリスト
                        {
                            "type": "rich_text_list",
                            "style": "ordered",
                            "indent": 0,
                            "elements": [
                                {
                                    "type": "rich_text_section",
                                    "elements": [{"type": "text", "text": "ボタンを押すと登録フォームが開きます"}]
                                },
                                {
                                    "type": "rich_text_section",
                                    "elements": [{"type": "text", "text": "フォームに必要事項を入力してSubmitボタンを押します"}]
                                }
                            ]
                        },
                        # 2番の補足（黒丸・インデント）
                        {
                            "type": "rich_text_list",
                            "style": "bullet",
                            "indent": 1,
                            "elements": [
                                {
                                    "type": "rich_text_section",
                                    "elements": [{"type": "text", "text": "[実行者＋経理] のDMグループ宛てにメッセージが送信されます"}]
                                }
                            ]
                        },
                        # 3番のリスト（offsetを使って3から開始）
                        {
                            "type": "rich_text_list",
                            "style": "ordered",
                            "indent": 0,
                            "offset": 2, # 前のリストが2つだったので、2つ分飛ばして「3」から開始
                            "elements": [
                                {
                                    "type": "rich_text_section",
                                    "elements": [
                                        {
                                            "type": "text",
                                            "text": "メッセージのスレッドに請求書PDFを添付して投稿します",
                                            "style": {"bold": True}
                                        }
                                    ]
                                }
                            ]
                        },
                        # 3番の補足（黒丸・インデント）
                        {
                            "type": "rich_text_list",
                            "style": "bullet",
                            "indent": 1,
                            "elements": [
                                {
                                    "type": "rich_text_section",
                                    "elements": [{"type": "text", "text": "Googleドライブの所定のフォルダにPDFファイルが格納されます"}]
                                }
                            ]
                        }
                    ]
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "請求書登録を開始する"
                            },
                            "style": "primary",
                            "action_id": "open_invoice_click"
                        }
                    ]
                }
            ]
        print(f"DEBUG: Sending setup message with blocks: {blocks}")
        say(blocks=blocks, text="請求書登録の案内")
        
    @app.command("/invoice")
    def handle_invoice_command(ack, command, client, body):
        ack()
        view_id = open_loading_modal(client, body["trigger_id"])
        open_invoice_modal(client, command["user_id"], view_id, command["channel_id"])

    @app.action("open_invoice_click")
    def handle_invoice_button_click(ack, body, client):
        ack()
        
        trigger_id = body["trigger_id"]
        user_id = body["user"]["id"]
        channel_id = body["channel"]["id"]
        
        print(f"DEBUG: Button clicked by {user_id} in {channel_id}")

        # ローディングモーダルを表示
        view_id = open_loading_modal(client, trigger_id)
        
        # 本番モーダルへの更新処理（重い処理）を実行
        # 「常に割り当てる」設定なら、そのまま実行してOKです
        open_invoice_modal(client, user_id, view_id, channel_id)

    @app.shortcut("open_invoice_modal")
    def handle_invoice_shortcut(ack, body, client):
        ack()
        trigger_id = body["trigger_id"]
        user_id = body["user"]["id"]
        view_id = open_loading_modal(client, trigger_id)
        open_invoice_modal(client, user_id, view_id)

    # # ワークフローの「関数」ステップ（リンククリック）が呼ばれた時の処理
    # @app.function("open_invoice_func")
    # def handle_open_invoice_step(event, client, complete, fail):
    #     """
    #     ワークフローのリンクがクリックされた時に、請求書登録モーダルを起動する
    #     """
    #     try:
    #         print(f"DEBUG: Function event received: {event}")

    #         inputs = event.get("inputs", {})
    #         user_id = inputs.get("user_id")
    #         interactivity = inputs.get("interactivity", {})
    #         pointer = interactivity.get("interactivity_pointer")

    #         if not pointer:
    #             print(f"ERROR: interactivity_pointer still missing in inputs. Event: {event}")
    #             fail(error="インタラクティブポインターの取得に失敗しました。ワークフローの設定を確認してください。")
    #             return

    #         # モーダル表示
    #         view_id = open_loading_modal(client, pointer)
    #         # 完了報告
    #         complete(outputs={"success": True})

    #         open_invoice_modal(client, user_id, view_id)
    #         print(f"Workflow function executed successfully for user: {user_id}")

    #     except Exception as e:
    #         print(f"Error in handle_open_invoice_step: {e}")
    #         # 失敗したことをワークフローに報告
    #         fail(error=f"モーダルの起動中にエラーが発生しました: {str(e)}")

def open_loading_modal(client, trigger_id: str):   
    try:
        # まずローディングモーダルを開く（3秒以内）
        result = client.views_open(
            trigger_id=trigger_id,
            view=_create_loading_modal()
        )
        view_id = result["view"]["id"]
        return view_id
    except Exception as e:
        print(f"Error opening loading modal: {e}")
        return

def open_invoice_modal(client, user_id: str, view_id: str, channel_id: Optional[str] = None) -> None:
    # ここから時間のかかる処理を実行
    credentials = load_user_credentials(user_id)
    print(f"Loaded credentials for user {user_id}: {credentials is not None}")
    if not credentials:
        # Slackサービスに「画面を認証用に変えて」と頼む
        slack_service.update_to_auth_required_modal(client, view_id, user_id)
        return
    
    # Firestoreから最新フォルダ情報を取得
    folder_dict = get_department_folders_from_firestore()
    drive_service.init(credentials)
    # アクセス可能なフォルダだけに絞る
    folder_dict = drive_service.get_accessible_folders(folder_dict)
    print(f"folders : {folder_dict}")
    if folder_dict:
        folders = [
            {"label": v, "value": k} for k, v in sorted(folder_dict.items(), key=lambda x: x[1])
        ]
    else:
        # システム管理者、および、経理担当者にDMでエラー通知
        notify_firestore_error(client, slack_service, user_id, "部署フォルダ情報", channel_id)
        return
    
    expense_types = [
        {"label": "仕入", "value": "仕入"},
        {"label": "販管費", "value": "販管費"}
    ]

    currencies_dict = get_currencies_from_firestore()
    if currencies_dict:
        currencies = [
            {"label": v, "value": k} for k, v in sorted(currencies_dict.items(), key=lambda x: x[1])
        ]
    else:
        # システム管理者、および、経理担当者にDMでエラー通知
        notify_firestore_error(client, slack_service, user_id, "通貨情報", channel_id)
        return
    
    # モーダルを本来のフォームに更新
    try:
        print(f"[DEBUG] Attempting views_update for View ID: {view_id}")
        client.views_update(
            view_id=view_id,
            view=_create_invoice_modal(folders, expense_types, currencies)
        )
        print(f"[SUCCESS] views_update completed.")
    except Exception as e:
        print(f"[ERROR] views_update failed.")
        if hasattr(e, "response"):
            # Slack API が返してきた具体的なエラーコード（invalid_blocks, expired_view など）
            print(f"Slack Error Code: {e.response['error']}")
            if "response_metadata" in e.response:
                print(f"Error Metadata: {e.response['response_metadata']}")
        else:
            print(f"General Error: {str(e)}")

def _create_loading_modal() -> Dict:
    """
    ローディング中のモーダルを構築
    """
    return {
        "type": "modal",
        "callback_id": "invoice_modal_loading",
        "title": {
            "type": "plain_text",
            "text": "請求書情報"
        },
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":hourglass_flowing_sand: *読み込み中...*\n\nデータを取得しています。しばらくお待ちください。"
                }
            }
        ]
    }


def _create_invoice_modal(
    folders: List[Dict[str, str]],
    expense_types: List[Dict[str, str]],
    currencies: List[Dict[str, str]]
) -> Dict:
    """
    請求書情報入力モーダルを構築
    
    Args:
        folders: フォルダ選択肢のリスト
        expense_types: 費用種別選択肢のリスト
        currencies: 通貨のリスト
    
    Returns:
        モーダルビューの JSON
    """
    
    # フォルダ選択肢を構築
    folder_options = [
        {
            "text": {"type": "plain_text", "text": f["label"]},
            "value": f["value"]
        }
        for f in folders
    ]
    
    # 費用種別選択肢を構築
    expense_options = [
        {
            "text": {"type": "plain_text", "text": e["label"]},
            "value": e["value"]
        }
        for e in expense_types
    ]

    # 通貨選択肢を構築
    currency_options = [
        {
            "text": {"type": "plain_text", "text": e["label"]},
            "value": e["value"]
        }
        for e in currencies
    ]
    
    return {
        "type": "modal",
        "callback_id": "invoice_modal",
        "title": {
            "type": "plain_text",
            "text": "請求書情報"
        },
        "submit": {
            "type": "plain_text",
            "text": "Submit"
        },
        "blocks": [
            {
                "type": "input",
                "block_id": "folder_section",
                "label": {
                    "type": "plain_text",
                    "text": "保存先フォルダ"
                },
                "element": {
                    "type": "static_select",
                    "action_id": "folder_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "フォルダを選択"
                    },
                    "options": folder_options
                }
            },
            {
                "type": "input",
                "block_id": "deadline_section",
                "label": {
                    "type": "plain_text",
                    "text": "支払希望日（※翌々営業日以降を指定してください。必ずしも希望日での支払い手配ができるとは限りません。ご了承ください。）"
                },
                "element": {
                    "type": "datepicker",
                    "action_id": "deadline_select"
                }
            },
            {
                "type": "input",
                "block_id": "company_block",
                "label": {
                    "type": "plain_text",
                    "text": "支払先企業名（正式名称）"
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": "company_input",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "例: 株式会社〇〇〇"
                    }
                }
            },
            {
                "type": "input",
                "block_id": "expense_section",
                "label": {
                    "type": "plain_text",
                    "text": "費用種別"
                },
                "element": {
                    "type": "static_select",
                    "action_id": "expense_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "区分を選択"
                    },
                    "options": expense_options
                }
            },
            {
                "type": "input",
                "block_id": "currency_section",
                "label": {
                    "type": "plain_text",
                    "text": "通貨"
                },
                "element": {
                    "type": "static_select",
                    "action_id": "currency_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "通貨を選択"
                    },
                    "options": currency_options,
                    "initial_option": {
                        "text": {"type": "plain_text", "text": "日本円"},
                        "value": "JPY"
                    }
                }
            },
            {
                "type": "input",
                "block_id": "amount_block",
                "label": {
                    "type": "plain_text",
                    "text": "請求金額"
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": "amount_input",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "例: 100000"
                    }
                }
            },
            {
                "type": "input",
                "block_id": "notes_block",
                "label": {
                    "type": "plain_text",
                    "text": "連絡事項（最大30文字）"
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": "notes_input",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "特に連絡事項がなければ記入不要です"
                    },
                    "max_length": 30
                },
                "optional": True
            }
        ]
    }

def notify_firestore_error(client, slack_service, user_id, target, channel_id=None):
    """
    Firestoreからの情報取得失敗時の通知処理
    システム管理者・経理担当者・実行ユーザーにエラー通知
    """
    accounting_members = get_department_accounting_users_from_firestore()   
    system_admin_members = get_department_system_admin_members_from_firestore()
    combined_list = list(set(accounting_members + system_admin_members))
    dm_channel = slack_service.create_group_dm(combined_list)
    error_message = f"情報がDBから取得できません。オフィスインフラ担当者にご確認ください: {target}"
    if dm_channel:
        client.chat_postMessage(
            channel=dm_channel,
            text=error_message
        )
    # 実行ユーザーにもエラー通知
    if channel_id:
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text=error_message
        )

def handle_update_folders_info_lazy(command, client, body):
    """
    /update_folders_info コマンドの遅延処理ハンドラー
    """
    trigger_id = body["trigger_id"]
    user_id = command["user_id"]
    try:
        # まずローディングモーダルを開く（3秒以内）
        result = client.views_open(
            trigger_id=trigger_id,
            view=_create_loading_modal()
        )
        view_id = result["view"]["id"]
    except Exception as e:
        print(f"Error opening loading modal: {e}")
        return
    
    # Google Driveのフォルダ情報取得
    credentials = load_user_credentials(user_id)
    if not credentials:
            # Slackサービスに「画面を認証用に変えて」と頼む
            slack_service.update_to_auth_required_modal(client, view_id, user_id)
            return
    drive_service.init(credentials)
    try:
        folders_info = drive_service.list_target_folders_under_parent()
        save_folders_info_to_firestore(folders_info)
        
        # 完了通知（経理担当者）
        dm_members = get_department_accounting_users_from_firestore()
        dm_channel = slack_service.create_group_dm(dm_members)
        if dm_channel:
            if folders_info:
                folder_lines = [f"・{v}（{k}）" for k, v in sorted(folders_info.items(), key=lambda x: x[1])]
                folders_text = "\n".join(folder_lines)
            else:
                folders_text = "（フォルダ情報なし）"
            message = (
                f"<@{user_id}> */update_folders_info 処理完了*\nGoogle Driveのフォルダ情報がFirestoreに保存されました。\n"
                f"*`【最新フォルダ一覧】`*\n{folders_text}"
            )
            client.chat_postMessage(channel=dm_channel, text=message)
            
    except Exception as e:
        # 遅延処理中なので、エラーは ephemeral メッセージで通知
        client.chat_postEphemeral(
            channel=command["channel_id"],
            user=user_id,
            text=f"フォルダ情報更新中にエラーが発生しました。オフィスインフラ担当者に確認してください: {e}"
        )

def handle_update_folders_info_ack(ack):
    """
    /update_folders_info コマンドの即レスポンスハンドラー
    """
    ack() 