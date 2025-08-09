# app.py
import os
import json
import logging
import requests
from flask import Flask, request, jsonify, abort

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# === 환경변수 ===
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")          # ntn_... 또는 secret_...
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")  # 예: mondaysing
NOTION_VERSION = "2022-06-28"
NOTION_API = "https://api.notion.com/v1"

# === 유틸: 노션 텍스트 블록 추가 ===
def notion_append_text_block(page_id: str, text: str):
    if not NOTION_TOKEN:
        raise RuntimeError("NOTION_TOKEN is missing")
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
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}}]}
        }]
    }
    r = requests.patch(url, headers=headers, json=payload, timeout=15)
    # 디버깅 편하게 에러 메시지 표시
    try:
        r.raise_for_status()
    except requests.HTTPError as e:
        app.logger.error("Notion API error %s: %s", r.status_code, r.text[:500])
        raise e
    return r.json()

# === 라우트 ===
@app.get("/")
def root():
    return {"ok": True, "service": "monday-notion-webhook"}

@app.get("/health")
def health():
    return {"ok": True}

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        return {"ok": "webhook alive"}

    # 간단 인증
    if WEBHOOK_SECRET and request.headers.get("X-Webhook-Secret") != WEBHOOK_SECRET:
        abort(401)

    data = request.get_json(force=True, silent=True) or {}
    page_id = data.get("page_id")
    text = data.get("text", "응답: 헬로 받음 ✅")

    if not page_id:
        return jsonify({"error": "page_id is required"}), 400

    app.logger.info("Append to Notion page %s: %s", page_id, text)
    res = notion_append_text_block(page_id, text)
    return jsonify({"status": "ok", "notion_object": res.get("object", "")})
