"""
FastAPI + Slack Bolt メインアプリケーション
HTTP モード（Socket Mode 不使用）で Slack イベントを処理
"""
import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler
from config import config
from handlers.command_handler import register_command_handlers
from handlers.modal_handler import register_modal_handlers
from handlers.file_handler import register_file_handlers
from auth_router import router as auth_router


# ロギングの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Slack Bolt アプリケーションの初期化
app = App(
    token=config.slack_bot_token,
    signing_secret=config.slack_signing_secret,
    process_before_response=True  # HTTP モードで重要
)

# FastAPI アプリケーションの初期化
api = FastAPI(title="Slack Invoice App")

# OAuth2.0　★記述場所がここでよいか要検証
api.include_router(auth_router)

# Slack リクエストハンドラーの初期化
handler = SlackRequestHandler(app)

# ハンドラーの登録
register_command_handlers(app)
register_modal_handlers(app)
register_file_handlers(app)


# ========== API エンドポイント ==========

@api.post("/slack/events")
async def slack_events(req: Request):
    """
    Slack イベントエンドポイント
    Slack からのリクエストを処理
    """
    try:
        return await handler.handle(req)
    except Exception as e:
        logger.error(f"Error handling Slack event: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@api.get("/health")
async def health_check():
    """
    ヘルスチェック エンドポイント
    Cloud Run のヘルスチェックに使用
    """
    return {"status": "ok", "environment": config.environment}


@api.get("/")
async def root():
    """
    ルートエンドポイント
    """
    return {
        "message": "Slack Invoice Registration App",
        "version": "1.0.0",
        "environment": config.environment
    }


# ========== メイン実行 ==========

if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting Slack Invoice App in {config.environment} environment")
    logger.info(f"Listening on port {config.port}")
    
    uvicorn.run(
        api,
        host="0.0.0.0",
        port=config.port,
        log_level="info"
    )
