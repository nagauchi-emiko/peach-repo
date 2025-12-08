"""
スラッシュコマンド ハンドラー
"""
from typing import Optional, List, Dict
from datetime import datetime
from slack_bolt import App
from services.sheets_service import sheets_service
from services.slack_service import slack_service
from auth_router import load_credentials


def register_command_handlers(app: App) -> None:
    @app.command("/invoice")
    def handle_invoice_command(ack, command, client, body):
        ack()
        user_id = command["user_id"]
        credentials = load_credentials(user_id)
        if not credentials:
            auth_url = f"https://your-domain/auth/google?user_id={user_id}"
            client.chat_postEphemeral(
                channel=command["channel_id"],
                user=user_id,
                text=f"Google認証が必要です。こちらから認証してください: {auth_url}"
            )
            return
        # credentialsを使ってGoogle Sheets/Drive APIを呼び出す処理
        
        # フォルダ選択肢を取得
        folders = sheets_service.get_folders()
        if not folders:
            # デフォルト値
            folders = [
                {"label": "DP/コンサルティングG", "value": "folder_consulting"},
                {"label": "DP/アライアンスG", "value": "folder_alliance"},
                {"label": "DX", "value": "folder_dx"},
                {"label": "その他", "value": "folder_other"}
            ]
        
        # 経費区分を取得
        expense_types = sheets_service.get_expense_types()
        
        # モーダルを開く
        try:
            client.views_open(
                trigger_id=body["trigger_id"],
                view=_create_invoice_modal(folders, expense_types)
            )
        except Exception as e:
            print(f"Error opening modal: {e}")


def _create_invoice_modal(
    folders: List[Dict[str, str]],
    expense_types: List[Dict[str, str]]
) -> Dict:
    """
    請求書登録モーダルを構築
    
    Args:
        folders: フォルダ選択肢のリスト
        expense_types: 経費区分選択肢のリスト
    
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
                    "text": "支払期限"
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
