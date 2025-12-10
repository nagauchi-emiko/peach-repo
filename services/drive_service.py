"""
Google Drive サービス - PDF ファイルをアップロード
"""
import json
import io
import os
import pickle
from typing import Optional, Dict
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError
from config import config
from google.oauth2.credentials import Credentials  # 追加


class DriveService:
    """Google Drive 連携クラス（OAuth2.0ユーザー認証対応）"""
    
    SCOPES = [
        'https://www.googleapis.com/auth/drive'
    ]
    
    def __init__(self, user_id):
        """
        初期化
        Args:
            user_id: SlackユーザーID（クレデンシャルファイル名に使用）
        """
        try:
            token_path = os.path.join(os.path.dirname(__file__), "user_tokens", f"{user_id}.pickle")
            if not os.path.exists(token_path):
                raise FileNotFoundError(f"クレデンシャルファイルが見つかりません: {token_path}")
            with open(token_path, "rb") as token:
                credentials = pickle.load(token)
            self.credentials = credentials
            self.drive_service = build('drive', 'v3', credentials=self.credentials)
            self.folder_id = config.google_drive_folder_id
        except Exception as e:
            print(f"Error initializing DriveService: {e}")
            self.drive_service = None
    
    def upload_pdf(
        self,
        file_content: bytes,
        file_name: str,
        folder_name: str = "請求書",
        parent_folder_id: Optional[str] = None
    ) -> Optional[Dict]:
        """
        PDF ファイルを Google Drive にアップロード
        
        Args:
            file_content: ファイルの内容（バイナリ）
            file_name: ファイル名
            folder_name: 保存先フォルダ名（この下に保存）
            parent_folder_id: 親フォルダID。指定なければ config.google_drive_folder_id を使用
        
        Returns:
            アップロードしたファイルの情報 {"id": "...", "name": "...", "webViewLink": "..."}
            失敗時は None
        """
        print(f"upload_pdf関数: {file_name}")

        try:
            if not self.drive_service:
                return None
            
            parent_id = parent_folder_id or self.folder_id
            
            # 保存先フォルダを取得または作成
            target_folder_id = self._get_or_create_folder(folder_name, parent_id)
            if not target_folder_id:
                return None
            
            # ファイルをアップロード
            media = MediaIoBaseUpload(io.BytesIO(file_content), mimetype='application/pdf')
            file_metadata = {
                'name': file_name,
                'mimeType': 'application/pdf',
                'parents': [target_folder_id]
            }
            
            file = self.drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, webViewLink, createdTime'
            ).execute()
            
            print(f"upload_pdf関数 return直前: {file}")

            return {
                'id': file.get('id'),
                'name': file.get('name'),
                'webViewLink': file.get('webViewLink'),
                'createdTime': file.get('createdTime')
            }
        except HttpError as e:
            print(f"Error uploading PDF: {e}")
            return None
    
    def _get_or_create_folder(self, folder_name: str, parent_folder_id: str) -> Optional[str]:
        """
        指定された名前のフォルダが存在する場合は取得、ない場合は作成
        
        Args:
            folder_name: フォルダ名
            parent_folder_id: 親フォルダID
        
        Returns:
            フォルダID
        """
        try:
            # 既存フォルダを検索
            query = (
                f"name='{folder_name}' and "
                f"'{parent_folder_id}' in parents and "
                f"mimeType='application/vnd.google-apps.folder' and "
                f"trashed=false"
            )
            
            results = self.drive_service.files().list(
                q=query,
                spaces='drive',
                fields='files(id)',
                pageSize=1
            ).execute()
            
            files = results.get('files', [])
            if files:
                return files[0]['id']
            
            # フォルダが存在しない場合は作成
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_folder_id]
            }
            
            folder = self.drive_service.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()
            
            return folder.get('id')
        except HttpError as e:
            print(f"Error getting or creating folder: {e}")
            return None
    
    def get_file_download_url(self, file_id: str) -> Optional[str]:
        """
        ファイルのダウンロード URL を取得
        
        Args:
            file_id: ファイルID
        
        Returns:
            ダウンロードURL
        """
        try:
            if not self.drive_service:
                return None
            
            return f"https://drive.google.com/uc?id={file_id}&export=download"
        except Exception as e:
            print(f"Error getting download URL: {e}")
            return None

    def get_folders_in_shared_folder(folder_id, creds):
        """
        指定した共有フォルダ配下のフォルダ名を取得
        
        Args:
            folder_id: 取得対象の親フォルダID
            creds: Google OAuth2認証情報
        """
        try:
            # # Drive APIサービスの構築
            # service = build('drive', 'v3', credentials=creds)
            
            # クエリの作成（指定フォルダ配下のフォルダのみ取得）
            query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
            
            # API呼び出し
            results = drive_service.files().list(
                q=query,
                fields='files(id, name, createdTime, modifiedTime)',
                pageSize=100
            ).execute()
            
            folders = results.get('files', [])
            
            if not folders:
                print('フォルダが見つかりませんでした。')
                return []
            
            print(f'取得したフォルダ数: {len(folders)}')
            print('-' * 50)
            
            for folder in folders:
                print(f"フォルダ名: {folder['name']}")
                print(f"  ID: {folder['id']}")
                print(f"  作成日時: {folder.get('createdTime', 'N/A')}")
                print(f"  更新日時: {folder.get('modifiedTime', 'N/A')}")
                print('-' * 50)
            
            return folders
            
        except HttpError as error:
            print(f'エラーが発生しました: {error}')
            return []
