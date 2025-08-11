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
SUMMARY_KIND = "summary"

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

# /api/messages (GET) — kind 보존, summary는 text 비어도 통과
@app.get("/api/messages")
def list_messages():
    sid = request.args.get("sid") or request.cookies.get("sid")
    if not sid:
        return jsonify({"ok": False, "error": "no sid"}), 400

    raw = r.lrange(key_for(sid), 0, -1)
    items = []
    now_ms = int(time.time() * 1000)
    for s in raw:
        try:
            it = json.loads(s)
        except Exception:
            continue

        role = it.get("role")
        kind = it.get("kind")  # <-- 추가
        text = (it.get("text") or "").strip()
        ts = int(it.get("ts") or now_ms)
        if ts < 1_000_000_000_000:
            ts *= 1000
        hidden = bool(it.get("hidden", False))

        # summary는 빈 문자열 허용, 그 외는 기존 규칙 유지
        if kind == SUMMARY_KIND:
            if role is None:
                role = "system"
        else:
            if role not in ("user", "assistant") or not text:
                continue

        items.append({"role": role, "text": text, "ts": ts, "hidden": hidden, "kind": kind})
    return jsonify({"ok": True, "items": items})


# /api/messages (POST) — kind 보존, summary는 빈 문자열 허용 + 항상 hidden 취급
@app.post("/api/messages")
def save_messages_batch():
    data = request.get_json(silent=True)
    if data is None:
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
        role = it.get("role")
        kind = it.get("kind")
        text = (str(it.get("text") or "")).strip()
        try:
            ts = int(it.get("ts") or now_ms)
        except Exception:
            ts = now_ms
        if ts < 1_000_000_000_000:
            ts *= 1000

        if kind == SUMMARY_KIND:
            # 요약은 빈 텍스트 허용 + 항상 hidden 취급
            if role is None:
                role = "system"
            hidden = True
        else:
            hidden = bool(it.get("hidden", False))
            if role not in ("user", "assistant") or not text:
                continue

        payloads.append(json.dumps({"role": role, "text": text, "ts": ts, "hidden": hidden, "kind": kind}))

    if not payloads:
        return jsonify({"ok": True, "saved": 0})

    k = key_for(sid)
    with r.pipeline() as p:
        p.rpush(k, *payloads)
        p.ltrim(k, -MAX_ITEMS, -1)
        p.expire(k, TTL_SECONDS)
        p.execute()
    return jsonify({"ok": True, "saved": len(payloads)})


# /api/chat — summary는 컨텍스트에서 제외(혹시 hidden이 false여도 가드)
@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    raw_prompt = (data.get("prompt") or "").strip()
    history = data.get("history") or []

    # visible & non-summary만 컨텍스트로
    hist = []
    for h in history:
        if h.get("hidden"):  # hidden 제외
            continue
        if h.get("kind") == SUMMARY_KIND:  # 요약 제외
            continue
        role = "assistant" if h.get("role") == "assistant" else "user"
        hist.append({"role": role, "text": str(h.get("text") or ""), "ts": int(h.get("ts") or 0)})

    # 이하 기존 로직(스탬프 제거/now 전달/토큰 트렁케이션)이 그대로라면 유지
    # ...


@app.get("/health")
def health():
    try:
        r.ping()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500

from werkzeug.exceptions import HTTPException

@app.errorhandler(404)
def handle_404(e):
    if request.path.startswith('/api/'):
        return jsonify({"ok": False, "error": "not found", "path": request.path}), 404
    return e, 404  # 페이지 라우트는 기존대로

@app.errorhandler(Exception)
def handle_exception(e):
    if request.path.startswith('/api/'):
        if isinstance(e, HTTPException):
            return jsonify({"ok": False, "error": e.description}), e.code
        # 예기치 못한 에러
        return jsonify({"ok": False, "error": str(e)}), 500
    raise e  # 페이지 라우트는 기존대로


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
