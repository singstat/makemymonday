# app.py
import os,sys,requests
from flask import Flask, render_template, request
import redis
import json

app = Flask(__name__, static_folder="static", template_folder="templates")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
r = redis.from_url(REDIS_URL, decode_responses=True)


OPENAI_API_KEY = os.environ.get("OPEN_AI_KEY")

@app.route("/api/ai", methods=["POST"])
def ai_proxy():
    if not OPENAI_API_KEY:
        return {"ok": False, "error": "OPENAI_API_KEY not configured"}, 500

    data = request.get_json(force=True, silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return {"ok": False, "error": "empty prompt"}, 400

    try:
        # 최소 동작 예시: Chat Completions (모델/파라미터는 필요에 맞게 조정)
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "You are a concise assistant."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2,
            },
            timeout=60
        )
        if resp.status_code != 200:
            return {"ok": False, "error": f"OpenAI {resp.status_code}: {resp.text[:200]}"} , 500
        j = resp.json()
        out = j.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        return {"ok": True, "output": out}, 200
    except Exception as e:
        print(f"[AI ERROR] {e}", file=sys.stdout, flush=True)
        return {"ok": False, "error": str(e)}, 500

@app.route("/health")
def health():
    return "ok", 200

@app.route("/test")
def test_page():
    # templates/test.html 을 렌더링
    return render_template("test.html")

@app.route("/api/save_messages", methods=["POST"])
def save_messages():
    data = request.get_json(force=True, silent=True) or {}
    page = (data.get("page") or "unknown").strip().strip("/")
    key = f"{page}_message"  # 규칙 적용: /test -> test_message, /sdf -> sdf_message
    r.set(key, json.dumps(data.get("messages", []), ensure_ascii=False))
    print("save message calling")
    return {"ok": True, "key": key, "saved": len(data.get("messages", []))}, 200

@app.route("/api/messages", methods=["GET"])
def get_messages():
    page = (request.args.get("page") or "unknown").strip().strip("/")
    key = f"{page}_message"
    raw = r.get(key) if r else None
    messages = []
    if raw:
        try:
            messages = json.loads(raw)
        except Exception:
            messages = []
    return {
        "ok": True,
        "exists": bool(raw),
        "key": key,
        "messages": messages
    }, 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))  # Railway는 PORT 환경변수를 설정함
    app.run(host="0.0.0.0", port=port)
