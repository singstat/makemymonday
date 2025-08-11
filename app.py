# app.py
import os
import json
import uuid
import time
import re
from datetime import datetime, timezone, timedelta

from flask import Flask, render_template, request, jsonify, make_response
import redis
from openai import OpenAI

# -------------------------
# Config & Clients
# -------------------------
app = Flask(__name__, template_folder="templates", static_folder="static")
app.url_map.strict_slashes = False

REDIS_URL = os.getenv("REDIS_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_KEY")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL 환경변수가 필요합니다.")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY 또는 OPEN_AI_KEY 환경변수가 필요합니다.")

r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
oa = OpenAI(api_key=OPENAI_API_KEY)

MAX_ITEMS = 1000                  # 사용자별 최대 저장 개수
TTL_SECONDS = 60 * 60 * 24 * 30   # 30일
KST = timezone(timedelta(hours=9))
STAMP_RE = re.compile(r"\b(\d{4})\s(\d{2})\s(\d{2})\s(\d{2})\s(\d{2})\s*$")

def key_for(sid: str) -> str:
    return f"msgs:{sid}"

# -------------------------
# Helpers
# -------------------------
def _normalize_history(history):
    """클라에서 온 history를 안전하게 정규화"""
    out = []
    for it in history or []:
        role = "assistant" if (it.get("role") == "assistant") else "user"
        text = str(it.get("text") or "")
        try:
            ts = int(it.get("ts") or 0)
        except Exception:
            ts = 0
        out.append({"role": role, "text": text, "ts": ts})
    return out

def _truncate_history(hist, max_items=20, max_chars=6000):
    """뒤에서부터 잘라 총 길이 제한"""
    acc, total = [], 0
    for item in reversed(hist):
        s = item["text"]
        length = len(s)
        if len(acc) >= max_items or (total + length) > max_chars:
            break
        acc.append(item)
        total += length
    return list(reversed(acc))

def _strip_kst_stamp(s: str):
    """
    문자열 끝의 'YYYY MM DD HH mm' (KST)을 제거하고,
    파싱 성공 시 'YYYY-MM-DD HH:MM KST' 문자열 반환
    """
    m = STAMP_RE.search(s)
    if not m:
        return s, None
    y, mo, d, h, mi = map(int, m.groups())
    try:
        dt_kst = datetime(y, mo, d, h, mi, tzinfo=KST)
        cleaned = STAMP_RE.sub("", s).rstrip()
        return cleaned, dt_kst.strftime("%Y-%m-%d %H:%M KST")
    except ValueError:
        return s, None

# -------------------------
# Routes
# -------------------------
@app.get("/")
def home():
    # URL의 ?sid=... 우선 → 없으면 쿠키 → 없으면 신규 발급
    qs_sid = request.args.get("sid")
    sid = qs_sid or request.cookies.get("sid") or uuid.uuid4().hex
    resp = make_response(render_template("ui.html"))  # templates/ui.html
    resp.set_cookie("sid", sid, max_age=TTL_SECONDS, samesite="Lax")
    return resp

@app.get("/api/messages")
def list_messages():
    """서버에 저장된 히스토리 조회 (이미 업로드된 것만)"""
    sid = request.args.get("sid") or request.cookies.get("sid")
    if not sid:
        return jsonify({"ok": False, "error": "no sid"}), 400

    raw = r.lrange(key_for(sid), 0, -1)
    items = []
    for s in raw:
        try:
            it = json.loads(s)
        except Exception:
            continue
        # 엄격 파싱: role/text 필수
        role = it.get("role")
        text = (it.get("text") or "").strip()
        ts = int(it.get("ts") or 0)
        if not text or role not in ("user", "assistant"):
            continue
        if ts and ts < 1_000_000_000_000:  # sec → ms 보정
            ts *= 1000
        items.append({"role": role, "text": text, "ts": ts or int(time.time() * 1000)})

    return jsonify({"ok": True, "items": items})

@app.post("/api/messages")
def save_messages_batch():
    """페이지 이탈 시 sendBeacon으로 일괄 업로드"""
    data = request.get_json(silent=True)
    if data is None:
        # 일부 브라우저에서 text/plain으로 올 수 있음
        try:
            data = json.loads(request.data.decode("utf-8"))
        except Exception:
            return jsonify({"ok": False, "error": "bad json"}), 400

    sid = data.get("sid") or request.cookies.get("sid")
    items = data.get("items")
    if not sid or not isinstance(items, list):
        return jsonify({"ok": True, "saved": 0})

    payloads = []
    now_ms = int(time.time() * 1000)
    for it in items:
        text = (str(it.get("text") or "")).strip()
        role = str(it.get("role") or "")
        try:
            ts = int(it.get("ts") or now_ms)
        except Exception:
            ts = now_ms
        if not text or role not in ("user", "assistant"):
            continue
        if ts < 1_000_000_000_000:
            ts *= 1000
        payloads.append(json.dumps({"text": text, "role": role, "ts": ts}))

    if not payloads:
        return jsonify({"ok": True, "saved": 0})

    k = key_for(sid)
    with r.pipeline() as p:
        p.rpush(k, *payloads)
        p.ltrim(k, -MAX_ITEMS, -1)   # 마지막 MAX_ITEMS개만 유지
        p.expire(k, TTL_SECONDS)
        p.execute()

    return jsonify({"ok": True, "saved": len(payloads)})

@app.post("/api/chat")
def chat():
    """
    클라이언트가 보낸 prompt(끝에 KST 스탬프 포함)와
    현재 세션 history(로컬 누적분)를 함께 받아 OpenAI 호출.
    - 표시용으로는 user 텍스트 뒤에 KST 스탬프를 그대로 사용하지만,
      모델에 보낼 때는 스탬프를 제거하고, system에 현재시각(KST)을 전달.
    """
    data = request.get_json(silent=True) or {}
    raw_prompt = (data.get("prompt") or "").strip()
    history = _normalize_history(data.get("history"))
    hist = _truncate_history(history)

    # 현재시각 추출: 우선순위 = 히스토리 마지막 user → prompt
    now_kst_str = None

    # 히스토리 마지막 user 항목에서 스탬프 제거 시도
    last_user_idx = max((i for i, it in enumerate(hist) if it["role"] == "user"), default=-1)
    if last_user_idx >= 0:
        cleaned, now_str = _strip_kst_stamp(hist[last_user_idx]["text"])
        hist[last_user_idx]["text"] = cleaned
        if now_str:
            now_kst_str = now_str

    # 히스토리가 비었으면 prompt로 사용자 발화 생성 (+스탬프 제거)
    if not hist and raw_prompt:
        cleaned, now_str2 = _strip_kst_stamp(raw_prompt)
        if now_str2:
            now_kst_str = now_kst_str or now_str2
        hist = [{"role": "user", "text": cleaned, "ts": int(time.time() * 1000)}]

    # 메시지 빌드
    msgs = [{
        "role": "system",
        "content": (
            "You are Monday. Answer concisely in Korean when appropriate. "
            "If a current datetime is provided, interpret relative dates like "
            "'오늘/어제/이번 주' based on it."
        ),
    }]
    if now_kst_str:
        msgs.append({
            "role": "system",
            "content": f"Current datetime (KST): {now_kst_str}. Use this as 'now'.",
        })
    for it in hist:
        msgs.append({"role": it["role"], "content": it["text"]})

    try:
        res = oa.chat.completions.create(
            model="gpt-4o-mini",
            messages=msgs,
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

# -------------------------
# Entrypoint (dev)
# -------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
