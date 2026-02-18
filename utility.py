from config import config
from datetime import datetime, timedelta, date
import jpholiday
from services.firestore_service import get_department_accounting_users_from_firestore

# 経理担当者限定ミドルウェア
def accountant_only(body, next, ack, client):
    # ユーザーIDを安全に取得（コマンドなら 'user_id'、それ以外なら 'user'の中）
    user_id = body.get("user_id") or body.get("user", {}).get("id")
    
    # リストの判定（カンマ区切りの文字列でもリストでも対応可能にする）
    accounting_members = get_department_accounting_users_from_firestore()
    if isinstance(accounting_members, str):
        accounting_members = [m.strip() for m in accounting_members.split(",")]
    if user_id in accounting_members:
        return next()  # 経理担当者なら実行
    
    # --- 経理担当者以外の場合 ---
    ack()
    
    # チャンネルIDを安全に取得
    # コマンドなら 'channel_id'、それ以外なら 'channel'オブジェクトの中
    channel_id = body.get("channel_id") or body.get("channel", {}).get("id")
    # もしチャンネルIDが取れない場合はユーザーID（DM）に送る
    if not channel_id:
        channel_id = user_id

    client.chat_postEphemeral(
        channel=channel_id,
        user=user_id,
        text="❌ この操作は経理担当者のみが実行できます。"
    )

def is_business_day(target_date):
    """平日（土日以外）かつ祝日でないか判定"""
    # 5=土曜日, 6=日曜日
    if target_date.weekday() >= 5:
        return False
    # 祝日判定
    if jpholiday.is_holiday(target_date):
        return False
    return True

def get_n_business_days_later(start_date, n):
    """n営業日後の日付を計算"""
    days_count = 0
    current_date = start_date
    while days_count < n:
        current_date += timedelta(days=1)
        if is_business_day(current_date):
            days_count += 1
    return current_date