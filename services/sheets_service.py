"""
Google Sheets サービス - 管理スプレッドシートからデータを取得・更新
"""
import json
from typing import List, Dict, Optional
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from config import config


class SheetsService:
    """Google Sheets 連携クラス"""
    
    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    
    def __init__(self):
        """初期化"""
        try:
            # サービスアカウント認証情報を取得
            if config.environment == "development":
                # ローカル開発環境: JSONファイルから読み込み
                self.credentials = service_account.Credentials.from_service_account_file(
                    config.google_service_account_json,
                    scopes=self.SCOPES
                )
            else:
                # Cloud Run環境: Secret Manager から取得した JSON を解析
                service_account_info = json.loads(config.google_service_account_json)
                self.credentials = service_account.Credentials.from_service_account_info(
                    service_account_info,
                    scopes=self.SCOPES
                )
            
            self.sheets_service = build('sheets', 'v4', credentials=self.credentials)
            self.spreadsheet_id = config.management_spreadsheet_id
        except Exception as e:
            print(f"Error initializing SheetsService: {e}")
            self.sheets_service = None
    
    def get_folders(self, sheet_name: str = "フォルダ設定") -> List[Dict[str, str]]:
        """
        管理用スプレッドシートからフォルダ選択肢を取得
        
        Args:
            sheet_name: シートの名前（デフォルト: "フォルダ設定"）
        
        Returns:
            フォルダ情報のリスト [{"label": "DP/コンサルティングG", "value": "folder_id_1"}, ...]
        """
        try:
            if not self.sheets_service or not self.spreadsheet_id:
                return []
            
            # A1:B999 からデータを取得（ヘッダーを含む）
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{sheet_name}'!A1:B999"
            ).execute()
            
            rows = result.get('values', [])
            if not rows or len(rows) < 2:
                return []
            
            # ヘッダーをスキップして、フォルダ情報を構築
            folders = []
            for row in rows[1:]:
                if len(row) >= 2 and row[0] and row[1]:
                    folders.append({
                        "label": row[0],
                        "value": row[1]
                    })
            
            return folders
        except HttpError as e:
            print(f"Error getting folders: {e}")
            return []
    
    def get_expense_types(self, sheet_name: str = "経費区分") -> List[Dict[str, str]]:
        """
        管理用スプレッドシートから経費区分（仕入 or 販管費）を取得
        
        Args:
            sheet_name: シートの名前（デフォルト: "経費区分"）
        
        Returns:
            経費区分のリスト [{"label": "仕入", "value": "materials"}, {"label": "販管費", "value": "opex"}, ...]
        """
        try:
            if not self.sheets_service or not self.spreadsheet_id:
                # デフォルト値を返す
                return [
                    {"label": "仕入", "value": "materials"},
                    {"label": "販管費", "value": "opex"}
                ]
            
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{sheet_name}'!A1:B999"
            ).execute()
            
            rows = result.get('values', [])
            if not rows or len(rows) < 2:
                return [
                    {"label": "仕入", "value": "materials"},
                    {"label": "販管費", "value": "opex"}
                ]
            
            expense_types = []
            for row in rows[1:]:
                if len(row) >= 2 and row[0] and row[1]:
                    expense_types.append({
                        "label": row[0],
                        "value": row[1]
                    })
            
            return expense_types if expense_types else [
                {"label": "仕入", "value": "materials"},
                {"label": "販管費", "value": "opex"}
            ]
        except HttpError as e:
            print(f"Error getting expense types: {e}")
            return [
                {"label": "仕入", "value": "materials"},
                {"label": "販管費", "value": "opex"}
            ]
    
    def append_invoice_data(
        self,
        sheet_name: str = "請求書データ",
        data: Optional[Dict] = None
    ) -> bool:
        """
        請求書データをスプレッドシートに追記
        
        Args:
            sheet_name: シートの名前
            data: 追記するデータ
        
        Returns:
            成功時は True、失敗時は False
        """
        try:
            if not self.sheets_service or not self.spreadsheet_id or not data:
                return False
            
            # データを行形式に変換
            row = [
                data.get("timestamp", ""),
                data.get("user_id", ""),
                data.get("user_name", ""),
                data.get("folder", ""),
                data.get("deadline", ""),
                data.get("company", ""),
                data.get("expense_type", ""),
                data.get("amount", ""),
                data.get("notes", ""),
                data.get("status", "pending"),
                data.get("thread_ts", ""),
                data.get("drive_file_url", "")
            ]
            
            # append_row を使用してデータを追加
            self.sheets_service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{sheet_name}'!A:L",
                valueInputOption="USER_ENTERED",
                body={"values": [row]}
            ).execute()
            
            return True
        except HttpError as e:
            print(f"Error appending invoice data: {e}")
            return False
    
    def update_invoice_status(
        self,
        sheet_name: str = "請求書データ",
        row_index: int = 1,
        status: str = "completed",
        drive_file_url: str = ""
    ) -> bool:
        """
        請求書のステータスを更新
        
        Args:
            sheet_name: シートの名前
            row_index: 行のインデックス（1-based）
            status: ステータス（pending, completed, etc.）
            drive_file_url: Google Drive のファイルURL
        
        Returns:
            成功時は True、失敗時は False
        """
        try:
            if not self.sheets_service or not self.spreadsheet_id:
                return False
            
            # J列（ステータス）と L列（URL）を更新
            self.sheets_service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{sheet_name}'!J{row_index}",
                valueInputOption="USER_ENTERED",
                body={"values": [[status]]}
            ).execute()
            
            if drive_file_url:
                self.sheets_service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"'{sheet_name}'!L{row_index}",
                    valueInputOption="USER_ENTERED",
                    body={"values": [[drive_file_url]]}
                ).execute()
            
            return True
        except HttpError as e:
            print(f"Error updating invoice status: {e}")
            return False


# グローバルインスタンス
sheets_service = SheetsService()
