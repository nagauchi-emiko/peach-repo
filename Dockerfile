# マルチステージビルド
# ステージ1: Python 3.11 をベースに依存パッケージをインストール
FROM python:3.11-slim as builder

WORKDIR /app

# システム依存パッケージをインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 依存パッケージをインストール
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt


# ステージ2: ランタイムイメージ
FROM python:3.11-slim

WORKDIR /app

# ステージ1 からビルド成果物をコピー
COPY --from=builder /root/.local /root/.local

# パスを設定
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# アプリケーションコードをコピー
COPY . .

# ポート指定
EXPOSE 8080

# ヘルスチェック（Cloud Run が使用）
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health')" || exit 1

# アプリケーション起動
CMD ["python", "-m", "uvicorn", "main:api", "--host", "0.0.0.0", "--port", "8080"]
