import firebase_admin
from firebase_admin import credentials, firestore

# 1. Firestoreの初期化
# ローカル環境で実行する場合は、サービスアカウントキーのパスを指定してください。
cred = credentials.Certificate("C:\\Users\\nagauchi.emiko\\slack_invoice_app\\sandbox-nagauchi-cc008592af0c.json")
firebase_admin.initialize_app(cred)

# すでに初期化されているエラーを避けるための記述（Cloud Shellなどで実行する場合）
if not firebase_admin._apps:
    firebase_admin.initialize_app()

db = firestore.client()

# 2. 登録するブロックデータ（Pythonの構造体として定義）
# これがFirestore上では「Array of Maps」として保存されます
target_blocks = [
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*個別払請求書の登録はこちらから*"
      }
    },
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_list",
          "style": "ordered",
          "indent": 0,
          "elements": [
            {
              "type": "rich_text_section",
              "elements": [{"type": "text", "text": "ボタンを押すと登録フォームが開きます"}]
            },
            {
              "type": "rich_text_section",
              "elements": [{"type": "text", "text": "フォームに必要事項を入力してSubmitボタンを押します"}]
            }
          ]
        },
        {
          "type": "rich_text_list",
          "style": "bullet",
          "indent": 1,
          "elements": [
            {
              "type": "rich_text_section",
              "elements": [{"type": "text", "text": "[実行者＋経理] のDMグループ宛てにメッセージが送信されます"}]
            }
          ]
        },
        {
          "type": "rich_text_list",
          "style": "ordered",
          "indent": 0,
          "offset": 2,
          "elements": [
            {
              "type": "rich_text_section",
              "elements": [
                {
                  "type": "text",
                  "text": "メッセージのスレッドに請求書PDFを添付して投稿します",
                  "style": {"bold": False}
                }
              ]
            }
          ]
        },
        {
          "type": "rich_text_list",
          "style": "bullet",
          "indent": 1,
          "elements": [
            {
              "type": "rich_text_section",
              "elements": [{"type": "text", "text": "Googleドライブの所定のフォルダにPDFファイルが格納されます"}]
            }
          ]
        }
      ]
    },
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {"type": "text", "text": "※不明な点がある場合は、経理担当("},
            {"type": "user", "user_id": "U05UPHBV0GK"},
            {"type": "text", "text": ")までお問い合わせください"}
          ]
        }
      ]
    },
    # {
    #   "type": "image",
    #   "title": {
    #     "type": "plain_text",
    #     "text": "スレッドへのPDF投稿方法 📸",
    #     "emoji": True
    #   },
    #   "image_url": "https://storage.googleapis.com/setsubun/slackapp_how_to_post.png",
    #   "alt_text": "スレッドにPDFを投稿する方法の解説画像"
    # },
    {
      "type": "actions",
      "elements": [
        {
          "type": "button",
          "text": {
            "type": "plain_text",
            "text": "請求書登録を開始する"
          },
          "style": "primary",
          "action_id": "open_invoice_click"
        }
      ]
    }
]

# 3. Firestoreへの保存実行
def save_to_firestore():
    doc_ref = db.collection("settings").document("invoice_setup_message")
    
    # データをセット（既存のデータは上書きされます）
    doc_ref.set({
        "blocks": target_blocks
    })
    print("Successfully updated Firestore: settings/invoice_setup_message")

if __name__ == "__main__":
    save_to_firestore()