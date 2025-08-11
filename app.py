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
def _normalize_history(history):
    out = []
    for it in history or []:
        role = 'assistant' if (it.get('role') == 'assistant') else 'user'
        text = str(it.get('text') or '')
        ts = int(it.get('ts') or 0)
        out.append({'role': role, 'text': text, 'ts': ts})
    return out

def _truncate_history(hist, max_items=20, max_chars=6000):
    # 뒤에서부터 max_items, 총 길이 max_chars 넘지 않도록 자름
    acc, total = [], 0
    for item in reversed(hist):
        s = item['text']
        length = len(s)
        if len(acc) >= max_items or (total + length) > max_chars:
            break
        acc.append(item)
        total += length
    return list(reversed(acc))

@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    raw_prompt = (data.get("prompt") or "").strip()
    history = _normalize_history(data.get("history"))

    # 히스토리가 있으면 그걸 컨텍스트로 쓰고, 없으면 prompt만 사용
    hist = _truncate_history(history)

    # '현재시각' 파생: 우선순위 = 히스토리 마지막 user → prompt
    now_kst_str = None

    def strip_stamp(s: str):
        m = STAMP_RE.search(s)
        if not m:
            return s, None
        y, mo, d, h, mi = map(int, m.groups())
        try:
            dt_kst = datetime(y, mo, d, h, mi, tzinfo=KST)
            return STAMP_RE.sub("", s).rstrip(), dt_kst.strftime("%Y-%m-%d %H:%M KST")
        except ValueError:
            return s, None

    # 히스토리 마지막 user에서 stamp 시도
    last_user_idx = max((i for i, it in enumerate(hist) if it['role'] == 'user'), default=-1)
    if last_user_idx >= 0:
        clean, now_str = strip_stamp(hist[last_user_idx]['text'])
        hist[last_user_idx]['text'] = clean
        if now_str:
            now_kst_str = now_str

    # 히스토리가 비었으면 prompt로 사용자 발화 생성 (+stamp 제거)
    chat_messages = [{
        "role": "system",
        "content": (
            "You are Monday. Answer concisely in Korean when appropriate. "
            "If a current datetime is provided, interpret relative dates like "
            "'오늘/어제/이번 주' based on it."
        ),
    }]
    if not hist and raw_prompt:
        cleaned, now_str2 = strip_stamp(raw_prompt)
        if now_str2: now_kst_str = now_kst_str or now_str2
        hist = [{"role": "user", "text": cleaned, "ts": int(time.time()*1000)}]

    if now_kst_str:
        chat_messages.append({
            "role": "system",
            "content": f"Current datetime (KST): {now_kst_str}. Use this as 'now'.",
        })

    for it in hist:
        chat_messages.append({"role": it["role"], "content": it["text"]})

    try:
        res = oa.chat.completions.create(
            model="gpt-4o-mini",
            messages=chat_messages,
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
