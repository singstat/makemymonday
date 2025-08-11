# app.py
import os, json, uuid, time, re
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, request, jsonify, make_response
import redis
from openai import OpenAI

app = Flask(__name__, template_folder="templates", static_folder="static")
app.url_map.strict_slashes = False

# Env
REDIS_URL = os.getenv("REDIS_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_KEY")
if not REDIS_URL: raise RuntimeError("REDIS_URL 필요")
if not OPENAI_API_KEY: raise RuntimeError("OPENAI_API_KEY 또는 OPEN_AI_KEY 필요")

# Clients
r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
oa = OpenAI(api_key=OPENAI_API_KEY)

# Const
MAX_ITEMS = 1000
TTL_SECONDS = 60*60*24*30
KST = timezone(timedelta(hours=9))
STAMP_RE = re.compile(r'\b(\d{4})\s(\d{2})\s(\d{2})\s(\d{2})\s(\d{2})\s*$')

# (참고) 입력 토큰 예산 — 서버에서도 안전차단(대략치)
BUDGET_TOKENS = 8000
RESERVED_TOKENS = 1000

def key_for(sid: str) -> str: return f"msgs:{sid}"

def approx_tokens(s: str) -> int:
    # 대략 2자=1토큰 가정 (보수적)
    return max(1, len(s) // 2)

def truncate_by_tokens(hist, budget=BUDGET_TOKENS - RESERVED_TOKENS):
    acc, used = [], 0
    for item in reversed(hist):
        t = approx_tokens(item["text"])
        if used + t > budget: break
        acc.append(item); used += t
    return list(reversed(acc))

def _strip_kst_stamp(s: str):
    m = STAMP_RE.search(s)
    if not m: return s, None
    y, mo, d, h, mi = map(int, m.groups())
    try:
        dt_kst = datetime(y, mo, d, h, mi, tzinfo=KST)
        cleaned = STAMP_RE.sub("", s).rstrip()
        return cleaned, dt_kst.strftime("%Y-%m-%d %H:%M KST")
    except ValueError:
        return s, None

@app.get("/")
def home():
    qs_sid = request.args.get("sid")
    sid = qs_sid or request.cookies.get("sid") or uuid.uuid4().hex
    resp = make_response(render_template("ui.html"))
    resp.set_cookie("sid", sid, max_age=TTL_SECONDS, samesite="Lax")
    return resp

@app.get("/api/messages")
def list_messages():
    """Redis에 저장된 모든 항목을 그대로 반환 (hidden 포함)"""
    sid = request.args.get("sid") or request.cookies.get("sid")
    if not sid: return jsonify({"ok": False, "error": "no sid"}), 400

    raw = r.lrange(key_for(sid), 0, -1)
    items = []
    now_ms = int(time.time()*1000)
    for s in raw:
        try:
            it = json.loads(s)
        except Exception:
            continue
        role = it.get("role")
        text = (it.get("text") or "").strip()
        if role not in ("user", "assistant") or not text:
            continue
        ts = int(it.get("ts") or now_ms)
        if ts < 1_000_000_000_000: ts *= 1000
        hidden = bool(it.get("hidden", False))
        items.append({"role": role, "text": text, "ts": ts, "hidden": hidden})
    return jsonify({"ok": True, "items": items})

@app.post("/api/messages")
def save_messages_batch():
    """
    페이지 이탈 시 업로드. 항목 하나하나에 hidden 플래그가 있을 수 있음.
    body: { sid, items: [{role, text, ts, hidden?}, ...] }
    """
    data = request.get_json(silent=True)
    if data is None:
        try: data = json.loads(request.data.decode("utf-8"))
        except Exception: return jsonify({"ok": False, "error": "bad json"}), 400

    sid = data.get("sid") or request.cookies.get("sid")
    items = data.get("items")
    if not sid or not isinstance(items, list): return jsonify({"ok": True, "saved": 0})

    payloads = []
    now_ms = int(time.time()*1000)
    for it in items:
        role = it.get("role")
        text = (str(it.get("text") or "")).strip()
        if role not in ("user", "assistant") or not text:
            continue
        try: ts = int(it.get("ts") or now_ms)
        except Exception: ts = now_ms
        if ts < 1_000_000_000_000: ts *= 1000
        hidden = bool(it.get("hidden", False))
        payloads.append(json.dumps({"role": role, "text": text, "ts": ts, "hidden": hidden}))

    if not payloads: return jsonify({"ok": True, "saved": 0})

    k = key_for(sid)
    with r.pipeline() as p:
        p.rpush(k, *payloads)
        p.ltrim(k, -MAX_ITEMS, -1)
        p.expire(k, TTL_SECONDS)
        p.execute()
    return jsonify({"ok": True, "saved": len(payloads)})

@app.post("/api/chat")
def chat():
    """
    클라에서 온 history를 컨텍스트로 사용.
    - 클라는 이미 토큰 예산을 맞춰 visible/hidden 분리하지만
      서버에서도 한번 더 토큰 예산 방어적으로 적용.
    - user 텍스트의 KST 스탬프는 제거해 system now로 전달.
    """
    data = request.get_json(silent=True) or {}
    raw_prompt = (data.get("prompt") or "").strip()
    history = data.get("history") or []

    # visible만 추려서 토큰 예산 내 잘라 사용
    hist = [{"role": ("assistant" if h.get("role")=="assistant" else "user"),
             "text": str(h.get("text") or ""),
             "ts": int(h.get("ts") or 0)}
            for h in history if not h.get("hidden")]

    hist = truncate_by_tokens(hist)

    # now 시각 추출: 마지막 user에서 스탬프 제거 시도 → 없으면 prompt에서
    now_kst_str = None
    for i in range(len(hist)-1, -1, -1):
        if hist[i]["role"] == "user":
            cleaned, now_str = _strip_kst_stamp(hist[i]["text"])
            hist[i]["text"] = cleaned
            if now_str: now_kst_str = now_str
            break
    if not now_kst_str and raw_prompt:
        _, now2 = _strip_kst_stamp(raw_prompt)
        if now2: now_kst_str = now2

    msgs = [{
        "role": "system",
        "content": (
            "You are Monday. Answer concisely in Korean when appropriate. "
            "If a current datetime is provided, interpret relative dates like "
            "'오늘/어제/이번 주' based on it."
        ),
    }]
    if now_kst_str:
        msgs.append({"role": "system", "content": f"Current datetime (KST): {now_kst_str}. Use this as 'now'."})
    for it in hist:
        msgs.append({"role": it["role"], "content": it["text"]})
    if not hist and raw_prompt:
        # 히스토리 없으면 프롬프트만 사용 (스탬프 제거는 위에서 처리)
        cleaned, _ = _strip_kst_stamp(raw_prompt)
        msgs.append({"role": "user", "content": cleaned})

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
