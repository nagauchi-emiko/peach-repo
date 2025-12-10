Slackスラッシュコマンドから呼び出したユーザーのOAuth認証でGoogle Workspace（GWS）のスプレッドシートやドライブを操作するには、
Google OAuth 2.0認証フローを組み込み、ユーザーごとにアクセストークンを取得・保存し、そのトークンでAPIを呼び出す必要があります。

この機能を実現するには、SlackアプリがSlackユーザーのIDをキーとして、個々のユーザーのGoogle Driveアクセストークンを安全に保存・管理する必要があります。
トークンストレージ: Slack ユーザー ID に紐づけて、Google Drive のアクセストークンとリフレッシュトークンを保存・取得する仕組み（データベースなど）を用意します。

実装の流れ
1.Google OAuth 2.0認証エンドポイントの追加
・FastAPIで /auth/google などの認証開始エンドポイントを作成
・Googleの認証URLにリダイレクト

2.Google認証コールバックエンドポイントの追加
・/auth/google/callback で認証後の処理
・認証コードを受け取り、アクセストークン・リフレッシュトークンを取得
・ユーザーID（Slackのuser_idなど）と紐付けてDBやファイルに保存

3.スラッシュコマンド実行時のトークン取得・API呼び出し
・コマンド実行時、呼び出しユーザーのGoogleトークンを取得
・そのトークンでGoogle Sheets/Drive APIを呼び出す


主要な修正ポイント（例）
1. 認証開始エンドポイント
```
from fastapi import APIRouter
from google_auth_oauthlib.flow import Flow

router = APIRouter()

@router.get("/auth/google")
async def google_auth_start(user_id: str):
    flow = Flow.from_client_secrets_file(
        "client_secret.json",
        scopes=["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"],
        redirect_uri="https://your-domain/auth/google/callback"
    )
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline', include_granted_scopes='true', state=user_id)
    return RedirectResponse(auth_url)
```

2. 認証コールバックエンドポイント
```
@router.get("/auth/google/callback")
async def google_auth_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")  # Slack user_id
    flow = Flow.from_client_secrets_file(
        "client_secret.json",
        scopes=["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"],
        redirect_uri="https://your-domain/auth/google/callback"
    )
    flow.fetch_token(code=code)
    credentials = flow.credentials
    # credentials.token, credentials.refresh_token, credentials.expiry などを state(user_id)と紐付けて保存
```

3. コマンドハンドラーでトークン取得・API呼び出し
```
def handle_invoice_command(...):
    user_id = command["user_id"]
    # user_idに紐付いたGoogleトークンを取得
    credentials = get_user_google_credentials(user_id)
    if not credentials:
        # 認証URLをSlackに送信して認証を促す
        client.chat_postEphemeral(channel=..., user=user_id, text="Google認証が必要です。こちらから認証してください: https://your-domain/auth/google?user_id=...")
        return
    # credentialsを使ってGoogle Sheets/Drive APIを呼び出す    from fastapi import APIRouter
    from google_auth_oauthlib.flow import Flow
    
    router = APIRouter()
    
    @router.get("/auth/google")
    async def google_auth_start(user_id: str):
        flow = Flow.from_client_secrets_file(
            "client_secret.json",
            scopes=["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"],
            redirect_uri="https://your-domain/auth/google/callback"
        )
        auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline', include_granted_scopes='true', state=user_id)
        return RedirectResponse(auth_url)        from fastapi import APIRouter
        from google_auth_oauthlib.flow import Flow
        
        router = APIRouter()
        
        @router.get("/auth/google")
        async def google_auth_start(user_id: str):
            flow = Flow.from_client_secrets_file(
                "client_secret.json",
                scopes=["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"],
                redirect_uri="https://your-domain/auth/google/callback"
            )
            auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline', include_granted_scopes='true', state=user_id)
            return RedirectResponse(auth_url)            from fastapi import APIRouter
            from google_auth_oauthlib.flow import Flow
            
            router = APIRouter()
            
            @router.get("/auth/google")
            async def google_auth_start(user_id: str):
                flow = Flow.from_client_secrets_file(
                    "client_secret.json",
                    scopes=["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"],
                    redirect_uri="https://your-domain/auth/google/callback"
                )
                auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline', include_granted_scopes='true', state=user_id)
                return RedirectResponse(auth_url)                from fastapi import APIRouter
                from google_auth_oauthlib.flow import Flow
                
                router = APIRouter()
                
                @router.get("/auth/google")
                async def google_auth_start(user_id: str):
                    flow = Flow.from_client_secrets_file(
                        "client_secret.json",
                        scopes=["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"],
                        redirect_uri="https://your-domain/auth/google/callback"
                    )
                    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline', include_granted_scopes='true', state=user_id)
                    return RedirectResponse(auth_url)
```

必要な追加・修正
Google Cloud ConsoleでOAuthクライアントIDを作成し、client_secret.jsonを取得
ユーザーごとにトークンを保存する仕組み（DBやファイルなど）
Slackコマンド実行時に認証済みか判定し、未認証なら認証URLを案内
認証済みならそのトークンでGoogle APIを操作
参考ライブラリ
google-auth-oauthlib
google-api-python-client
ご要望があれば、具体的なファイル修正例やDB設計例も提示できます。
まずはこの流れで設計・実装してください。