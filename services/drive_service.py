"""
Google Drive サービス - PDF ファイルをアップロード
"""
import json
import io
from typing import Optional, Dict
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError
from config import config
from auth_router import load_credentials
import re
from typing import Optional, Dict, List, Set
from google.cloud import firestore

class DriveService:
    """Google Drive 連携クラス（OAuth2.0ユーザー認証対応）"""
    
    SCOPES = [
        'https://www.googleapis.com/auth/drive'
    ]
    
    def __init__(self):
        print(f"DriveService.__init__")
    
    def init(self, user_id: str):
        """
        初期化
        Args:
            credentials: google.oauth2.credentials.Credentials インスタンス（ユーザーごとの認証情報）
        """
        try:
            self.credentials = load_credentials(user_id)
            self.drive_service = build('drive', 'v3', credentials=self.credentials)
            # Firestoreからfolder_idを取得
            try:
                db = firestore.Client()
                doc = db.collection("folders_info").document("config").get()
                if doc.exists:
                    self.folder_id = doc.to_dict().get("google_drive_folder_id")
                else:
                    self.folder_id = None
            except Exception as e:
                print(f"Firestoreからfolder_id取得エラー: {e}")
                self.folder_id = None
        except Exception as e:
            print(f"Error initializing DriveService: {e}")
            self.drive_service = None

    def upload_pdf(
        self,
        file_content: bytes,
        file_name: str,
        yyyymm: str,
        parent_folder_id: str
    ) -> Optional[Dict]:
        """
        PDF ファイルを Google Drive にアップロード
        
        Args:
            file_content: ファイルの内容（バイナリ）
            file_name: ファイル名
            yyyymm: 保存先フォルダ名（この下に保存）（yyyymmもしくは、〆済yyyymmを取得または作成）
            parent_folder_id: 親フォルダID
        
        Returns:
            アップロードしたファイルの情報 {"id": "...", "name": "...", "webViewLink": "..."}
            失敗時は None
        """
        print(f"upload_pdf関数: {file_name}")

        try:
            if not self.drive_service:
                return None
            
            print(f"parent_folder_id: {parent_folder_id}")

            # 保存先フォルダを取得または作成
            target_folder_id = self._get_or_create_folder(yyyymm, parent_folder_id)
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
                fields='id, name, webViewLink, createdTime',
                supportsAllDrives=True
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
    
    def _get_or_create_folder(self, yyyymm: str, parent_folder_id: str) -> Optional[str]:
        """
        指定された名前のフォルダが存在する場合は取得、ない場合は作成
        
        Args:
            yyyymm: フォルダ名（yyyymmもしくは、〆済yyyymmを取得または作成）
            parent_folder_id: 親フォルダID（部署グループフォルダID）
        
        Returns:
            フォルダID
        """
        try:
            # 既存フォルダを検索
            query = (
                f"(name='{yyyymm}' or name='〆済{yyyymm}') and "
                f"'{parent_folder_id}' in parents and "
                f"mimeType='application/vnd.google-apps.folder' and "
                f"trashed=false"
            )
            
            print(f"query: {query}")

            results = self.drive_service.files().list(
                q=query,
                spaces='drive',
                fields='files(id)',
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                pageSize=1
            ).execute()

            print(f"query results: {results}")
            
            files = results.get('files', [])
            if files:
                return files[0]['id']
            
            # フォルダが存在しない場合は作成
            folder_metadata = {
                'name': yyyymm,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_folder_id]
            }
            
            folder = self.drive_service.files().create(
                body=folder_metadata,
                fields='id',
                supportsAllDrives=True
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

    def _list_child_folders_raw(self, parent_folder_id: str) -> list[dict]:
        """
        指定フォルダ直下にあるサブフォルダをそのまま返す内部用メソッド
        戻り値: [{"id": "...", "name": "..."}, ...]
        """
        try:
            if not self.drive_service:
                return []

            query = (
                f"'{parent_folder_id}' in parents and "
                f"mimeType='application/vnd.google-apps.folder' and "
                f"trashed=false"
            )

            folders: list[dict] = []
            page_token = None

            while True:
                response = self.drive_service.files().list(
                    q=query,
                    spaces='drive',
                    fields='nextPageToken, files(id, name)',
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    pageToken=page_token,
                    pageSize=100
                ).execute()

                items = response.get("files", [])
                for item in items:
                    folders.append({
                        "id": item.get("id"),
                        "name": item.get("name"),
                    })

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

            return folders

        except HttpError as e:
            print(f"Error listing child folders (raw): {e}")
            return []

    def list_target_folders_under_parent(
        self,
        parent_folder_id: Optional[str] = None,
    ) -> dict:
        """
        フォルダIDをキー、フォルダ名（またはB/Cラベル）を値とする辞書を返す。
        """
        # Firestoreから除外フォルダ（カード決済明細、【経理作業用】など）のIDを取得
        try:
            db = firestore.Client()
            doc = db.collection("folders_info").document("exclude_folder_ids").get()
            if doc.exists:
                exclude_folder_ids = doc.to_dict().get("exclude_folder_ids", [])
            else:
                exclude_folder_ids = []
        except Exception as e:
            print(f"Firestore exclude_folder_ids取得エラー: {e}")
            exclude_folder_ids = []

        """
        親フォルダ(A)直下のフォルダ(B)およびその直下フォルダ(C)を走査し、
        仕様に従ってフォルダ情報を返す。

        仕様:
        - A 直下の B は、そのままはリストに含めない
        - B 直下の C について、「B/C」というラベルで返す
          * 「過去分」という名前は除外
          * フォルダ名に 6 桁連続の数字 (例: 202512) を含む場合は除外
        - ただし、B 直下のフォルダが
          「6桁連続の数字を含むフォルダ名のフォルダ」および
          「過去分」という名前のフォルダ「だけ」で構成されている場合、
          B 自体を 1 件としてリストに含める
        - 「過去分」という名前のフォルダは、B/C いずれもリストに含めない
        - ひ孫フォルダ（A/B/C/D）は見に行かない
        - exclude_folder_ids に含まれるフォルダIDは、
          そのフォルダ自身およびその配下を一切リストに含めない
        - 返り値
          フォルダIDをキー、フォルダ名（またはB/Cラベル）を値とする辞書
        """
        if not self.drive_service:
            return {}

        parent_id = parent_folder_id or self.folder_id
        exclude_folder_ids = set(exclude_folder_ids)

        # 親フォルダ(A) 直下のフォルダ(B)を取得
        def _list_child_folders_once(p_id: str) -> List[Dict[str, str]]:
            query = (
                f"'{p_id}' in parents and "
                f"mimeType='application/vnd.google-apps.folder' and "
                f"trashed=false"
            )
            folders: List[Dict[str, str]] = []
            page_token = None

            while True:
                resp = self.drive_service.files().list(
                    q=query,
                    spaces='drive',
                    fields='nextPageToken, files(id, name)',
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    pageToken=page_token,
                    pageSize=100,
                ).execute()

                for f in resp.get("files", []):
                    folders.append({"id": f["id"], "name": f["name"]})

                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
            return folders

        folder_dict = {}
        digit6_pattern = re.compile(r"\d{6}")

        # A 直下の B
        b_folders = _list_child_folders_once(parent_id)
        for b in b_folders:
            b_id = b["id"]
            b_name = b["name"]

            # B 自体が exclude 対象なら、その配下も含めて無視
            if b_id in exclude_folder_ids:
                continue

            # B 直下の C を取得
            c_folders = _list_child_folders_once(b_id)

            # exclude 対象を除外
            c_folders = [c for c in c_folders if c["id"] not in exclude_folder_ids]

            if not c_folders:
                # C が何もない場合は B を含めない（仕様上「だけで構成」ではないため）
                continue

            # C のうち、「過去分」「6桁連続数字を含む名前」かどうかを判定
            valid_cs: List[Dict[str, str]] = [] # 条件を満たしてリストに入れる C
            only_excluded_types = True  # B 直下が「過去分」or「6桁数字含む」だけかどうか
            for c in c_folders:
                c_name = c["name"]

                is_past_folder = (c_name == "過去分")
                has_6digits = bool(digit6_pattern.search(c_name))

                # 有効な C（=リストに入れる C）
                if (not is_past_folder) and (not has_6digits):
                    valid_cs.append(c)
                    only_excluded_types = False  # 有効な C が 1つでもあるので「だけ」ではなくなる
                else:
                    # 「過去分」または「6桁連続数字を含む」フォルダ
                    # → 仕様によりリストには含めない
                    # ただし B を 1件として含めるかどうかの判定には使うため、
                    # only_excluded_types フラグには影響させない（初期値 True のまま）
                    pass

            # valid_cs があれば、「B/C」というラベルで C を結果に追加
            if valid_cs:
                for c in valid_cs:
                    folder_dict[c["id"]] = f"{b_name}/{c['name']}"
            else:
                # 有効な C が存在しない場合
                # B 直下が「過去分」or「6桁連続数字含む」だけで構成されているなら B 自体を 1件追加
                if only_excluded_types:
                    folder_dict[b_id] = b_name
        return folder_dict
        
#グローバルクラス
drive_service = DriveService()