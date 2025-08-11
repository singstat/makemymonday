# app.py
import os, json, uuid, time
from flask import Flask, render_template, request, jsonify, make_response
import redis
from openai import OpenAI

import re
from datetime import datetime, timezone, timedelta
KST = timezone(timedelta(hours=9))
STAMP_RE = re.compile(r'\b(\d{4})\s(\d{2})\s(\d{2})\s(\d{2})\s(\d{2})\s*$')

app = Flask(__name__, template_folder="templates", static_folder="static")
app.url_map.strict_slashes = False

# --- env ---
REDIS_URL = os.getenv("REDIS_URL")
OPEN_AI_KEY = os.getenv("OPEN_AI_KEY")
if not REDIS_URL: raise RuntimeError("REDIS_URL 필요")
if not OPEN_AI_KEY: raise RuntimeError("OPEN_AI_KEY 필요")

# --- clients ---
r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
oa = OpenAI(api_key=OPEN_AI_KEY)

MAX_ITEMS = 1000
TTL_SECONDS = 60*60*24*30  # 30일

def key_for(sid: str) -> str: return f"msgs:{sid}"

@app.get("/")
def home():
    sid = request.cookies.get("sid") or uuid.uuid4().hex
    resp = make_response(render_template("ui.html"))  # templates/ui.html
    resp.set_cookie("sid", sid, max_age=TTL_SECONDS, samesite="Lax")
    return resp

# 히스토리 조회 (서버에 저장된 것만)
@app.get("/api/messages")
def list_messages():
    sid = request.args.get("sid") or request.cookies.get("sid")
    if not sid: return jsonify({"ok": False, "error": "no sid"}), 400
    items = []
    for s in r.lrange(key_for(sid), 0, -1):
        try:
            it = json.loads(s)
            if isinstance(it, dict) and "text" in it and "role" in it:
                # 보정
                it["ts"] = int(it.get("ts") or int(time.time()*1000))
                items.append(it)
        except Exception:
            pass
    return jsonify({"ok": True, "items": items})

# 배치 저장 (페이지 이탈 시 sendBeacon으로 업로드)
@app.post("/api/messages")
def save_messages_batch():
    data = request.get_json(silent=True)
    if data is None:
        try: data = json.loads(request.data.decode("utf-8"))
        except Exception: return jsonify({"ok": False, "error": "bad json"}), 400
    sid = data.get("sid") or request.cookies.get("sid")
    items = data.get("items")
    if not sid or not isinstance(items, list): return jsonify({"ok": True, "saved": 0})

    payloads = []
    now = int(time.time()*1000)
    for it in items:
        text = (it.get("text") or "").strip()
        role = (it.get("role") or "").strip()
        ts = int(it.get("ts") or now)
        if text and role in ("user", "assistant"):
            payloads.append(json.dumps({"text": text, "role": role, "ts": ts}))
    if not payloads: return jsonify({"ok": True, "saved": 0})

    k = key_for(sid)
    with r.pipeline() as p:
        p.rpush(k, *payloads)
        p.ltrim(k, -MAX_ITEMS, -1)
        p.expire(k, TTL_SECONDS)
        p.execute()
    return jsonify({"ok": True, "saved": len(payloads)})

# ChatGPT 프록시 (입력은 KST 시간이 붙은 문자열이 들어옴)
@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    raw = (data.get("prompt") or "").strip()
    if not raw:
        return jsonify({"ok": False, "error": "empty prompt"}), 400

    # 끝에 붙은 "YYYY MM DD HH mm" (KST) 추출 → system에 현재시각으로 전달
    user_text = raw
    now_kst_str = None
    m = STAMP_RE.search(raw)
    if m:
        y, mo, d, h, mi = map(int, m.groups())
        try:
            dt_kst = datetime(y, mo, d, h, mi, tzinfo=KST)
            now_kst_str = dt_kst.strftime("%Y-%m-%d %H:%M KST")
            user_text = STAMP_RE.sub("", raw).rstrip()  # 숫자는 본문에서 제거
        except ValueError:
            now_kst_str = None  # 잘못된 날짜면 무시

    messages = [
        {
            "role": "system",
            "content": (
                "You are Monday. Answer concisely in Korean when appropriate. "
                "If the current datetime is provided below, treat all relative dates "
                "like '오늘/어제/이번 주' based on it."
            ),
        },
    ]
    if now_kst_str:
        messages.append({
            "role": "system",
            "content": f"Current datetime (KST): {now_kst_str}. Use this as 'now'.",
        })
    messages.append({"role": "user", "content": user_text})

    try:
        res = oa.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
        )
        reply = (res.choices[0].message.content or "").strip()
        return jsonify({"ok": True, "reply": reply})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.get("/health")
def health():
    try:
        r.ping()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
