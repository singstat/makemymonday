import os
import requests
from flask import Flask, request, jsonify, abort

app = Flask(__name__)

NOTION_TOKEN = os.environ["NOTION_TOKEN"]      # Railway Shared Variables에 넣은 ntn_... 토큰
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "mondaysing")  # Railway에 넣은 웹훅 비밀번호
NOTION_VERSION = "2022-06-28"
NOTION_API = "https://api.notion.com/v1"


def notion_append_text_block(page_id: str, text: str):
    url = f"{NOTION_API}/blocks/{page_id}/children"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    payload = {
        "children": [{
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": text}}]
            }
        }]
    }
    r = requests.patch(url, headers=headers, json=payload, timeout=10)
    r.raise_for_status()
    return r.json()

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/webhook")
def webhook():
    # 웹훅 비밀번호 확인
    if WEBHOOK_SECRET and request.headers.get("X-Webhook-Secret") != WEBHOOK_SECRET:
        abort(401)

    data = request.get_json(force=True, silent=True) or {}
    page_id = data.get("page_id")
    text = data.get("text", "응답: 헬로 받음 ✅")

    if not page_id:
        return jsonify({"error": "page_id is required"}), 400

    result = notion_append_text_block(page_id, text)
    return jsonify({"status": "ok", "notion_result": result.get("object", "")})
