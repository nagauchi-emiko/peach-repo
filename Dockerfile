# Python 3.12 のスリム版を使用
FROM python:3.12-slim

# 作業ディレクトリ
WORKDIR /app

# コンテナ起動時に .pyc ファイルを作成させない設定（軽量化）
ENV PYTHONDONTWRITEBYTECODE=1
# ログがバッファリングされず、すぐに Cloud Run のログに出力されるようにする
ENV PYTHONUNBUFFERED=1

# ビルドに必要なシステムパッケージをインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 依存パッケージをインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ソースコードや JSON ファイルをすべてコピー
COPY . .

# Cloud Run の環境変数 PORT を使用して起動
CMD python -m uvicorn main:api --host 0.0.0.0 --port $PORT

# # マルチステージビルド
# # ステージ1: Python 3.11 をベースに依存パッケージをインストール
# FROM python:3.11-slim as builder

# WORKDIR /app

# # システム依存パッケージをインストール
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     build-essential \
#     && rm -rf /var/lib/apt/lists/*

# # 依存パッケージをインストール
# COPY requirements.txt .
# RUN pip install --user --no-cache-dir -r requirements.txt


# # ステージ2: ランタイムイメージ
# FROM python:3.12-slim

# WORKDIR /app

# # ステージ1 からビルド成果物をコピー
# COPY --from=builder /root/.local /root/.local

# # パスを設定
# ENV PATH=/root/.local/bin:$PATH
# ENV PYTHONUNBUFFERED=1
# # ENV PORT=8080   <-- この行は削除（Cloud Run側で設定されるため）

# # アプリケーションコードをコピー
# COPY . .

# # ポート指定
# EXPOSE 8080

# # # ヘルスチェック（Cloud Run が使用）
# # HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
# #     CMD python -c "import requests; requests.get('http://localhost:8080/health')" || exit 1

# # アプリケーション起動
# # CMD ["python", "-m", "uvicorn", "main:api", "--host", "0.0.0.0", "--port", "%PORT%"]
# CMD python -m uvicorn main:api --host 0.0.0.0 --port $PORT