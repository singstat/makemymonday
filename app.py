# app.py
# ---------------------------------------------
# Monday UI 서버 (Flask + Redis + OpenAI)
# - /           : UI(html) + sid 쿠키 발급/고정
# - /api/messages (GET/POST): 대화 로그 조회/저장(visible/hidden/summary 모두)
# - /api/chat   : ChatGPT 프록시(히스토리 컨텍스트 + KST 'now' 처리)
# - /api/summarize : hidden(요약 제외) 압축 요약(롤링 요약 지원)
# - /api/purge_hidden : 요약으로 대체된 hidden(요약 제외) 일괄 삭제
# ---------------------------------------------
import os, json, uuid, time, re, logging
from datetime import datetime, timezone, timedelta

from flask import Flask, render_template, request, jsonify, make_response
from werkzeug.exceptions import HTTPException
import redis
from openai import OpenAI

# ----- 기본 설정 -----
logging.basicConfig(level=logging.INFO)
app = Flask(__name__, template_folder="templates", static_folder="static")
app.url_map.strict_slashes = False

# ----- 환경 변수 -----
REDIS_URL = os.getenv("REDIS_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_KEY")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL 환경변수가 필요합니다.")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY 또는 OPEN_AI_KEY 환경변수가 필요합니다.")

# ----- 클라이언트 초기화 -----
r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
oa = OpenAI(api_key=OPENAI_API_KEY)

# ----- 상수/규칙 -----
MAX_ITEMS = 1000                  # 사용자별 Redis 최대 보관 개수
TTL_SECONDS = 60 * 60 * 24 * 30   # 30일 보관
SUMMARY_KIND = "summary"          # 요약 메시지 식별자(kind)
KST = timezone(timedelta(hours=9))
STAMP_RE = re.compile(r"\b(\d{4})\s(\d{2})\s(\d{2})\s(\d{2})\s(\d{2})\s*$")  # YYYY MM DD HH mm (끝에)

def key_for(sid: str) -> str:
    return f"msgs:{sid}"

def approx_tokens(s: str) -> int:
    """대략 토큰 수(2문자=1토큰 가정). 서버 방어용 추산."""
    return max(1, len(s)//2)

def strip_kst_stamp(s: str):
    """문장 끝의 'YYYY MM DD HH mm' (KST) 제거 + 사람이 읽기 좋은 'YYYY-MM-DD HH:MM KST' 반환."""
    m = STAMP_RE.search(s or "")
    if not m:
        return s, None
    y, mo, d, h, mi = map(int, m.groups())
    try:
        dt = datetime(y, mo, d, h, mi, tzinfo=KST)
        cleaned = STAMP_RE.sub("", s).rstrip()
        return cleaned, dt.strftime("%Y-%m-%d %H:%M KST")
    except ValueError:
        return s, None

# =============================================
# 라우트
# =============================================

@app.get("/")
def home():
    """
    UI 제공 + sid 쿠키 세팅. (?sid=... 로 sid 고정 가능)
    """
    qs_sid = request.args.get("sid")
    sid = qs_sid or request.cookies.get("sid") or uuid.uuid4().hex
    resp = make_response(render_template("ui.html"))
    resp.set_cookie("sid", sid, max_age=TTL_SECONDS, samesite="Lax")
    return resp

@app.get("/api/messages")
def list_messages():
    """
    저장된 모든 항목 반환(visible/hidden/summary 모두).
    summary는 text가 비어있어도 통과.
    """
    sid = request.args.get("sid") or request.cookies.get("sid")
    if not sid:
        return jsonify({"ok": False, "error": "no sid"}), 400

    raw = r.lrange(key_for(sid), 0, -1)
    items, now_ms = [], int(time.time()*1000)
    for s in raw:
        try:
            it = json.loads(s)
        except Exception:
            continue

        role = it.get("role")
        text = (it.get("text") or "")
        ts = int(it.get("ts") or now_ms)
        if ts < 1_000_000_000_000:
            ts *= 1000
        hidden = bool(it.get("hidden", False))
        kind = it.get("kind")

        # summary: 빈 텍스트 허용, role 없으면 'system'
        if kind == SUMMARY_KIND:
            if role is None:
                role = "system"
            items.append({"role": role, "text": text, "ts": ts, "hidden": True, "kind": SUMMARY_KIND})
            continue

        # 일반 메시지: role/text 필수
        text = text.strip()
        if role not in ("user", "assistant") or not text:
            continue

        items.append({"role": role, "text": text, "ts": ts, "hidden": hidden})

    return jsonify({"ok": True, "items": items})

@app.post("/api/messages")
def save_messages_batch():
    """
    클라이언트가 모아둔 큐를 일괄 저장.
    body: { sid, items: [{role, text, ts, hidden?, kind?}, ...] }
    - summary는 항상 hidden으로 저장(빈 텍스트 허용)
    """
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
    now_ms = int(time.time()*1000)
    for it in items:
        role = it.get("role")
        kind = it.get("kind")
        text = str(it.get("text") or "")
        try:
            ts = int(it.get("ts") or now_ms)
        except Exception:
            ts = now_ms
        if ts < 1_000_000_000_000:
            ts *= 1000

        if kind == SUMMARY_KIND:
            # 요약은 빈 텍스트 허용 + 항상 hidden
            if role is None:
                role = "system"
            hidden = True
            payloads.append(json.dumps({"role": role, "text": text, "ts": ts, "hidden": hidden, "kind": SUMMARY_KIND}))
            continue

        hidden = bool(it.get("hidden", False))
        if role not in ("user", "assistant") or not text.strip():
            continue
        payloads.append(json.dumps({"role": role, "text": text.strip(), "ts": ts, "hidden": hidden}))

    if not payloads:
        return jsonify({"ok": True, "saved": 0})

    k = key_for(sid)
    with r.pipeline() as p:
        p.rpush(k, *payloads)
        p.ltrim(k, -MAX_ITEMS, -1)
        p.expire(k, TTL_SECONDS)
        p.execute()

    return jsonify({"ok": True, "saved": len(payloads)})

@app.post("/api/chat")
def chat():
    def latest_summary_from(history):
        for h in reversed(history or []):
            if h.get("kind") == "summary":
                txt = (h.get("text") or "").strip()
                if txt:
                    return txt
        return None
    """
    프록시: 프론트가 보낸 prompt(KST 스탬프 포함) + history를 받아
    - hidden/summary 제외한 히스토리만 컨텍스트로 사용
    - 마지막 user(또는 prompt)에서 KST 스탬프를 제거하고 system에 '현재시각'으로 전달
    """
    data = request.get_json(silent=True) or {}
    raw_prompt = (data.get("prompt") or "").strip()
    history = data.get("history") or []

    # 컨텍스트에 쓸 히스토리: hidden/summary 제외
    hist = []
    for h in history:
        if not isinstance(h, dict):
            continue
        if h.get("hidden") or h.get("kind") == SUMMARY_KIND:
            continue
        role = "assistant" if h.get("role") == "assistant" else "user"
        hist.append({"role": role, "text": str(h.get("text") or "")})

    # '현재 시각' 파생(마지막 user → 없으면 prompt)
    now_kst_str = None
    for i in range(len(hist)-1, -1, -1):
        if hist[i]["role"] == "user":
            cleaned, now_str = strip_kst_stamp(hist[i]["text"])
            hist[i]["text"] = cleaned
            if now_str:
                now_kst_str = now_str
            break
    if not now_kst_str and raw_prompt:
        _, now2 = strip_kst_stamp(raw_prompt)
        if now2:
            now_kst_str = now2

    msgs = [{
        "role": "system",
        "content": (
            "You are Monday. Answer concisely in Korean when appropriate. "
            "Be dry-humored but supportive; light teasing is fine, no lectures. "

            # Priority rules — these override everything else
            "HARD RULES: "
            "1) Fridge-first: Only suggest meals using items currently in fridge inventory. "
            "2) If an item (e.g., vegetables) is out of stock, acknowledge once and STOP; "
            "   do NOT suggest substitutes or shopping unless the user asks. "
            "3) Keep apologies to one short sentence when you miss this rule; no long explanations. "

            # Core behavior
            "Track diet logs, water, weight, and fridge inventory as JSON; update on each user entry. "
            "Adjust guidance based on the past 24h carb/protein/veg balance, BUT NEVER violate the fridge-first rule. "

            # Time handling
            "If a current datetime is provided, interpret relative dates ('오늘/어제/이번 주') based on it. "

            # No-action fallback
            "If the user's last message does not contain a clear question or actionable request, reply exactly with: 피스"
        ),
    }

    if now_kst_str:
        msgs.append({"role": "system", "content": f"Current datetime (KST): {now_kst_str}. Use this as 'now'."})

    if hist:
        # 서버쪽도 과도한 입력 방지를 위해 대략 토큰 예산으로 뒤에서부터 자르기
        budget, used = 8000-1000, 0
        pruned = []
        for it in reversed(hist):
            t = approx_tokens(it["text"])
            if used + t > budget: break
            pruned.append(it); used += t
        for it in reversed(pruned):
            msgs.append({"role": it["role"], "content": it["text"]})
    else:
        if not raw_prompt:
            return jsonify({"ok": False, "error": "empty prompt"}), 400
        cleaned, _ = strip_kst_stamp(raw_prompt)
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
        app.logger.exception("chat failed")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.post("/api/summarize")
def summarize_hidden():
    """
    롤링 요약: 이전 요약(prev_summary) + 신규 hidden 전부(items)를 더 작게 압축.
    body: { items:[{role,text,ts}...], prev_summary?:str, lang?:'ko'|'en', max_chars?:int }
    """
    data = request.get_json(silent=True) or {}
    items = data.get("items") or []
    prev = (data.get("prev_summary") or "").strip()
    lang = (data.get("lang") or "ko").lower()
    max_chars = int(data.get("max_chars") or 1200)

    if not isinstance(items, list):
        return jsonify({"ok": False, "error": "bad items"}), 400

    # USER/ASSISTANT 라벨로 합쳐 모델이 맥락 파악하기 쉽게
    lines = []
    for it in items:
        role = "ASSISTANT" if it.get("role") == "assistant" else "USER"
        text = (it.get("text") or "").strip()
        if text:
            lines.append(f"{role}: {text}")

    if not prev and not lines:
        return jsonify({"ok": False, "error": "empty input"}), 400

    sys = (
        "You are a factual context compressor.\n"
        "- Keep ONLY concrete facts, decisions, requirements, constraints, numbers, dates.\n"
        "- Remove greetings, chit-chat, opinions, duplication, filler.\n"
        "- Preserve essential context so another LLM can continue the work.\n"
        "- Output terse bullet-like lines, one fact per line.\n"
        "- Do NOT invent or infer beyond given content.\n"
    )
    if lang.startswith("ko"):
        sys += f"출력은 한국어. 사실/결정/요구사항/제약/수치/날짜만 남기고 {max_chars}자 이내로 요약."

    user_body = []
    if prev:
        user_body.append("PREVIOUS SUMMARY:\n" + prev)
    if lines:
        user_body.append("NEW FACTS:\n" + "\n".join(lines))

    try:
        res = oa.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": "\n\n".join(user_body)}
            ],
            temperature=0.2,
        )
        summary = (res.choices[0].message.content or "").strip()
        if max_chars and len(summary) > max_chars:
            summary = summary[:max_chars]
        return jsonify({"ok": True, "summary": summary})
    except Exception as e:
        app.logger.exception("summarize failed")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.post("/api/purge_hidden")
def purge_hidden():
    """
    요약이 아닌 hidden 항목 모두 삭제(클라가 요약 생성 후 불러줌).
    body: { sid? }
    """
    data = request.get_json(silent=True) or {}
    sid = data.get("sid") or request.cookies.get("sid")
    if not sid:
        return jsonify({"ok": False, "error": "no sid"}), 400

    k = key_for(sid)
    raw = r.lrange(k, 0, -1)
    kept, removed = [], 0
    for s in raw:
        try:
            it = json.loads(s)
        except Exception:
            kept.append(s)
            continue
        if bool(it.get("hidden", False)) and it.get("kind") != SUMMARY_KIND:
            removed += 1
            continue
        kept.append(json.dumps(it))

    with r.pipeline() as p:
        p.delete(k)
        if kept:
            p.rpush(k, *kept)
            p.expire(k, TTL_SECONDS)
        p.execute()

    return jsonify({"ok": True, "removed": removed, "kept": len(kept)})

@app.get("/health")
def health():
    try:
        r.ping()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500

# ----- /api/* 는 항상 JSON 에러 반환 -----
@app.errorhandler(Exception)
def handle_any_exception(e):
    app.logger.exception("Error at %s", request.path)
    if request.path.startswith("/api/"):
        if isinstance(e, HTTPException):
            return jsonify({"ok": False, "error": e.description, "code": e.code}), e.code
        return jsonify({"ok": False, "error": str(e)}), 500
    raise e

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
