"""
スラッシュコマンド ハンドラー
"""
from typing import Optional, List, Dict
from datetime import datetime
from slack_bolt import App
from services.drive_service import drive_service
from services.firestore_service import get_department_folders_from_firestore
from services.slack_service import slack_service
from auth_router import load_credentials
from config import config
from services.firestore_service import save_folders_info_to_firestore


def register_command_handlers(app: App) -> None:
    @app.command("/update_folders_info")
    def handle_update_folders_info(ack, command, client, body):
        ack()
        user_id = command["user_id"]
        # 管理者チェック
        if user_id not in config.admin_group_members:
            client.chat_postEphemeral(
                channel=command["channel_id"],
                user=user_id,
                text="管理者でないメンバーがupdate_folders_infoコマンドを実行しようとしました。管理者のみがこのコマンドを実行できます。"
            )
            return

        # 1. Google Driveのフォルダ情報取得
        drive_service.init(user_id)
        try:
            folders_info = drive_service.list_target_folders_under_parent()
        except Exception as e:
            client.chat_postEphemeral(channel=command["channel_id"], user=user_id, text=f"フォルダ情報取得に失敗しました: {e}")
            return

        # 2. Firestoreへ上書き保存
        try:
            save_folders_info_to_firestore(folders_info)
        except Exception as e:
            client.chat_postEphemeral(channel=command["channel_id"], user=user_id, text=f"Firestore保存に失敗しました: {e}")
            return

        # 3. Slack DMグループに完了通知（department_foldersも掲載）
        try:
            dm_members = config.admin_group_members
            dm_channel = slack_service.create_group_dm(dm_members)
            if dm_channel:
                # フォルダ情報を整形
                if folders_info:
                    folder_lines = [f"・{v}（{k}）" for k, v in sorted(folders_info.items(), key=lambda x: x[1])]
                    folders_text = "\n".join(folder_lines)
                else:
                    folders_text = "（フォルダ情報なし）"
                message = (
                    "/update_folders_info コマンドの処理が完了しました。Google Driveのフォルダ情報がFirestoreに更新されました。\n"
                    "---\n"
                    f"【最新フォルダ一覧】\n{folders_text}"
                )
                slack_service.client.chat_postMessage(
                    channel=dm_channel,
                    text=message
                )
        except Exception as e:
            client.chat_postEphemeral(channel=command["channel_id"], user=user_id, text=f"DM通知に失敗しました: {e}")
            return
        
    @app.command("/invoice")
    def handle_invoice_command(ack, command, client, body):
        # trigger_idを先に保存
        trigger_id = body["trigger_id"]
        user_id = command["user_id"]
        # channel_id = command["channel_id"]
        
        # 即座にack()を呼び出し、ローディングモーダルを開く
        ack()
        
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
        
        # ここから時間のかかる処理を実行
        credentials = load_credentials(user_id)
        print(f"Loaded credentials for user {user_id}: {credentials is not None}")
        
        if not credentials:
            # auth_url = f"https://brentley-ungrafted-unmeaningfully.ngrok-free.dev/auth/google?user_id={user_id}"
            auth_url = f"{config.redirect_uri.replace('/callback','')}?user_id={user_id}"
            # モーダルを認証要求画面に更新
            client.views_update(
                view_id=view_id,
                view=_create_auth_required_modal(auth_url)
            )
            return
        
        # Firestoreから最新フォルダ情報を取得
        folder_dict = get_department_folders_from_firestore()
        print(f"folders : {folder_dict}")
        if folder_dict:
            folders = [
                {"label": v, "value": k} for k, v in sorted(folder_dict.items(), key=lambda x: x[1])
            ]
        else:
            # 管理者にDMでエラー通知
            admin_members = config.admin_group_members if config.admin_group_members else []
            dm_channel = slack_service.create_group_dm(admin_members)
            error_message = "共有ドライブの部署フォルダ情報がDBから取得できません。管理者にご確認ください。"
            if dm_channel:
                slack_service.client.chat_postMessage(
                    channel=dm_channel,
                    text=error_message
                )
            # 実行ユーザーにもエラー通知
            client.chat_postEphemeral(
                channel=command["channel_id"],
                user=user_id,
                text=error_message
            )
            return
        
        expense_types = [
            {"label": "仕入", "value": "仕入"},
            {"label": "販管費", "value": "販管費"}
        ]

        currencies = [
            {"label": "日本円", "value": "JPY"},
            {"label": "米ドル", "value": "USD"},
            {"label": "タイバーツ", "value": "THB"}
        ]
        
        # モーダルを本来のフォームに更新
        try:
            client.views_update(
                view_id=view_id,
                view=_create_invoice_modal(folders, expense_types, currencies)
            )
        except Exception as e:
            print(f"Error updating modal: {e}")


def _create_loading_modal() -> Dict:
    """
    ローディング中のモーダルを構築
    """
    return {
        "type": "modal",
        "callback_id": "invoice_modal_loading",
        "title": {
            "type": "plain_text",
            "text": "請求書登録"
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


def _create_auth_required_modal(auth_url: str) -> Dict:
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


def _create_invoice_modal(
    folders: List[Dict[str, str]],
    expense_types: List[Dict[str, str]],
    currencies: List[Dict[str, str]]
) -> Dict:
    """
    請求書登録モーダルを構築
    
    Args:
        folders: フォルダ選択肢のリスト
        expense_types: 経費区分選択肢のリスト
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
    
    # 経費区分選択肢を構築
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
            "text": "請求書登録"
        },
        "submit": {
            "type": "plain_text",
            "text": "登録"
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
                    "text": "経費区分"
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
                    "options": currency_options
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