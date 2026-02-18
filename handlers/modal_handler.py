"""
モーダル送信 ハンドラー
"""
from datetime import datetime
from slack_bolt import App
from services.slack_service import slack_service
from services.firestore_service import get_department_accounting_users_from_firestore
from config import config
from datetime import datetime, timedelta, date
import utility

"""
モーダル送信 ハンドラーを登録

Args:
    app: Slack Bolt アプリケーション
"""
def register_modal_handlers(app: App) -> None:    
    @app.view("invoice_modal")
    def handle_invoice_submission(ack, body, client, view):
        """
        請求書登録モーダル送信時の処理
        """
        # 支払希望日バリデーション
        values = view["state"]["values"]
        try:
            deadline = values["deadline_section"]["deadline_select"]["selected_date"]
            deadline_date = datetime.strptime(deadline, "%Y-%m-%d").date()
            today = date.today()
            # 2営業日後を計算
            min_allowed_date = utility.get_n_business_days_later(today, 2)
            if deadline_date < min_allowed_date:
                ack(response_action="errors",
                    errors={
                        "deadline_section": f"支払希望日は2営業日以降（{min_allowed_date}以降）の日付を指定してください。"
                    })
                return
        except Exception as e:
            print(f"Validation Error: {e}")
            # バリデーション自体の失敗を通知（これがないとタイムアウトする）
            ack(response_action="errors",
                errors={
                    "deadline_section": "日付の検証中にエラーが発生しました。"
                })
            return

        ack()
        print(f"★invoice_modal★: {body['user']['id']}")

        try:
            user_id = body["user"]["id"]
            timestamp = datetime.now().isoformat()
            folder = values["folder_section"]["folder_select"]["selected_option"]["text"]["text"]
            folder_id = values["folder_section"]["folder_select"]["selected_option"]["value"]
            company = values["company_block"]["company_input"]["value"]
            expense_type = values["expense_section"]["expense_select"]["selected_option"]["value"]
            currency = values["currency_section"]["currency_select"]["selected_option"]["value"]
            amount = values["amount_block"]["amount_input"]["value"]
            notes = values["notes_block"]["notes_input"].get("value") or ""
            
            # ユーザー情報を取得
            user_info = slack_service.get_user_info(user_id)
            user_name = user_info["real_name"] if user_info else user_id
            
            # 請求書データを構築
            invoice_data = {
                "timestamp": timestamp,
                "user_id": user_id,
                "user_name": user_name,
                "folder": folder,
                "folder_id": folder_id,
                "deadline": deadline,
                "company": company,
                "expense_type": expense_type,
                "currency": currency,
                "amount": amount,
                "notes": notes
            }
            
            # グループ DM を作成（実行ユーザー + 経理担当者）
            accounting_members = get_department_accounting_users_from_firestore()
            print(f"accounting_members: {accounting_members}")

            # accounting_users には複数のユーザーIDが含まれることを想定（カンマ区切り）
            if isinstance(accounting_members, list):
                group_members = [user_id] + accounting_members
            else:
                group_members = [user_id] + accounting_members.split(",")
            group_members = [m.strip() for m in group_members if m.strip()]
            
            print(f"group_menbers: {group_members}")

            # 重複を除去
            group_members = list(set(group_members))
            
            channel_id = slack_service.create_group_dm(group_members)
            if not channel_id:
                print(f"Failed to create group DM for users: {group_members}")
                return
            
            # メッセージを送信
            message_ts = slack_service.post_invoice_message(
                channel_id=channel_id,
                invoice_data=invoice_data,
                user_id=user_id
            )

        except Exception as e:
            print(f"Error handling invoice submission: {e}")
            import traceback
            traceback.print_exc()
            # 例外発生時にSlackモーダルへエラーを返す
            ack(response_action={
                "errors": {
                    "__all__": "エラーが発生しました。オフィスインフラ担当者に連絡してください。"
                }
            })
