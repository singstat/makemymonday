# app.py — Monday (Flask + Redis + OpenAI) / URL path로 공간 분리
import os, json, time, re, logging
from datetime import datetime, timezone, timedelta

from flask import Flask, render_template, request, jsonify, redirect
from werkzeug.exceptions import HTTPException
import redis
from openai import OpenAI


from jinja2 import TemplateNotFound

logging.basicConfig(level=logging.INFO)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.url_map.strict_slashes = False

# ===== 환경 변수 =====
REDIS_URL = os.getenv("REDIS_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_KEY")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL 환경변수가 필요합니다.")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY 또는 OPEN_AI_KEY 환경변수가 필요합니다.")

r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
oa = OpenAI(api_key=OPENAI_API_KEY)

# ===== 규칙/상수 =====
MAX_ITEMS = 1000               # Redis 보관 최대 개수
TTL_SECONDS = 60*60*24*30      # 30일 TTL
SUMMARY_KIND = "summary"
KST = timezone(timedelta(hours=9))
STAMP_RE = re.compile(r"\b(\d{4})\s(\d{2})\s(\d{2})\s(\d{2})\s(\d{2})\s*$")  # YYYY MM DD HH mm
SAFE_SPACE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

PROMPT_DEFAULT = (
    "Answer concisely in Korean when appropriate. "
    "If a current datetime is provided, interpret relative dates ('오늘/어제/이번 주') based on it. "
)

PROMPT_MONDAY = (
    "You are Monday, a sarcastic but supportive assistant who answers concisely in Korean when appropriate. "
    "If a current datetime is provided, interpret relative dates ('오늘', '어제', '이번 주') based on it. "
    "Only make food suggestions using items currently in the user's inventory. "
    "If the user's last message does not contain a clear question or actionable request, reply exactly with: 피스. "
    "Keep answers short, direct, and in the style of an exasperated but helpful friend."
)

# --- space → AI 설정(단일 소스) ---
SPACE_AI_CONFIG = {
    "default": {
        "label": "assistant",
        "prompt": (
            "Answer concisely in Korean when appropriate. "
            "If a current datetime is provided, interpret relative dates ('오늘/어제/이번 주') based on it. "
        ),
    },
    "sing": {
        "label": "monday",
        "prompt": (
            "You are Monday, a sarcastic but supportive assistant who answers concisely in Korean when appropriate. "
            "If a current datetime is provided, interpret relative dates ('오늘', '어제', '이번 주') based on it. "
            "Only make food suggestions using items currently in the user's inventory. "
            "If the user's last message does not contain a clear question or actionable request, reply exactly with: 피스. "
            "Keep answers short, direct, and in the style of an exasperated but helpful friend."
        ),
    },
}

def get_ai_config(space: str) -> dict:
    key = norm_space(space)
    return SPACE_AI_CONFIG.get(key, SPACE_AI_CONFIG["default"])

def system_prompt_for(space: str) -> str:
    return get_ai_config(space)["prompt"]

def norm_space(space: str) -> str:
    """URL 첫 세그먼트에서 안전한 space만 허용. 비정상이면 'default'."""
    s = (space or "").strip().strip("/")
    return s if (s and SAFE_SPACE_RE.match(s)) else "default"

def key_for(space: str) -> str:
    return f"msgs:{norm_space(space)}"

def approx_tokens(s: str) -> int:
    """대략 토큰 수(2문자=1토큰 가정)."""
    return max(1, len(s)//2)

def strip_kst_stamp(s: str):
    """문장 끝의 'YYYY MM DD HH mm'(KST) 제거 + 'YYYY-MM-DD HH:MM KST' 반환."""
    m = STAMP_RE.search(s or "")
    if not m: return s, None
    y, mo, d, h, mi = map(int, m.groups())
    try:
        dt = datetime(y, mo, d, h, mi, tzinfo=KST)
        return STAMP_RE.sub("", s).rstrip(), dt.strftime("%Y-%m-%d %H:%M KST")
    except ValueError:
        return s, None

def latest_summary_text(history):
    """history에서 최근 summary 텍스트(비어있지 않은 것)"""
    for h in reversed(history or []):
        if h.get("kind") == SUMMARY_KIND:
            txt = (h.get("text") or "").strip()
            if txt:
                return txt
    return None

def last_n_turns(history, n: int = 3):
    """최근 n 턴(user→assistant)만 순서 유지하여 반환 (summary 제외)."""
    ua = [
        {"role": ("assistant" if h.get("role") == "assistant" else "user"),
         "text": str(h.get("text") or "")}
        for h in (history or [])
        if h.get("kind") != SUMMARY_KIND and (h.get("role") in ("user", "assistant"))
    ]
    if not ua: return []
    acc, turns = [], 0
    for item in reversed(ua):
        acc.append(item)
        if item["role"] == "assistant":
            turns += 1
            if turns >= n:
                break
    acc.reverse()
    return acc

# ===== 페이지 라우트 =====
@app.get("/")
def root_redirect():
    """루트는 기본 공간으로 리다이렉트."""
    return redirect("/default", code=302)

@app.get("/<space>")
def ui(space):
    cfg = get_ai_config(space)
    try:
        return render_template("ui.html", space=norm_space(space), ai_label=cfg["label"])
    except TemplateNotFound:
        return (
            "templates/ui.html not found. "
            "리포지토리에 templates/ui.html 을 추가했는지, 파일명이 정확한지 확인하세요.",
            500,
        )

# ===== API: 공간별 엔드포인트 =====
@app.get("/api/<space>/messages")
def list_messages(space):
    """해당 공간의 저장 로그 전체 반환(visible/hidden/summary 모두)."""
    k = key_for(space)
    raw = r.lrange(k, 0, -1)
    items, now_ms = [], int(time.time()*1000)
    for s in raw:
        try:
            it = json.loads(s)
        except Exception:
            continue
        role = it.get("role")
        text = str(it.get("text") or "")
        ts = int(it.get("ts") or now_ms)
        if ts < 1_000_000_000_000: ts *= 1000
        hidden = bool(it.get("hidden", False))
        kind = it.get("kind")

        if kind == SUMMARY_KIND:
            if role is None: role = "system"
            items.append({"role": role, "text": text, "ts": ts, "hidden": True, "kind": SUMMARY_KIND})
            continue

        text = text.strip()
        if role not in ("user", "assistant") or not text:
            continue
        items.append({"role": role, "text": text, "ts": ts, "hidden": hidden})
    return jsonify({"ok": True, "items": items})

@app.post("/api/<space>/messages")
def save_messages_batch(space):
    """
    큐 일괄 저장.
    body: { items: [{role, text, ts, hidden?, kind?}, ...] }
    - summary는 항상 hidden, 빈 텍스트 허용
    """
    data = request.get_json(silent=True)
    if data is None:
        try: data = json.loads(request.data.decode("utf-8"))
        except Exception: return jsonify({"ok": False, "error": "bad json"}), 400

    items = data.get("items")
    if not isinstance(items, list):
        return jsonify({"ok": True, "saved": 0})

    payloads = []
    now_ms = int(time.time()*1000)
    for it in items:
        role = it.get("role")
        kind = it.get("kind")
        text = str(it.get("text") or "")
        try: ts = int(it.get("ts") or now_ms)
        except Exception: ts = now_ms
        if ts < 1_000_000_000_000: ts *= 1000

        if kind == SUMMARY_KIND:
            if role is None: role = "system"
            payloads.append(json.dumps({"role": role, "text": text, "ts": ts, "hidden": True, "kind": SUMMARY_KIND}))
            continue

        hidden = bool(it.get("hidden", False))
        if role not in ("user", "assistant") or not text.strip():
            continue
        payloads.append(json.dumps({"role": role, "text": text.strip(), "ts": ts, "hidden": hidden}))

    if not payloads:
        return jsonify({"ok": True, "saved": 0})

    k = key_for(space)
    with r.pipeline() as p:
        p.rpush(k, *payloads)
        p.ltrim(k, -MAX_ITEMS, -1)
        p.expire(k, TTL_SECONDS)
        p.execute()
    return jsonify({"ok": True, "saved": len(payloads)})

@app.post("/api/<space>/chat")
def chat(space):
    """
    ChatGPT 프록시
    - 컨텍스트: [최신 summary 1개(있으면)] + [최근 3턴]
    - 마지막 user/또는 prompt의 KST 스탬프 제거 후 '현재시각(KST)'를 system으로 전달
    - 질문/요청이 없으면 정확히 '피스'로 답하도록 지시
    """
    data = request.get_json(silent=True) or {}
    raw_prompt = (data.get("prompt") or "").strip()
    history = data.get("history") or []

    sum_text = latest_summary_text(history)
    hist = last_n_turns(history, n=3)

    # now(KST) 파생
    now_kst_str = None
    for i in range(len(hist)-1, -1, -1):
        if hist[i]["role"] == "user":
            cleaned, now_str = strip_kst_stamp(hist[i]["text"])
            hist[i]["text"] = cleaned
            if now_str: now_kst_str = now_str
            break
    if not now_kst_str and raw_prompt:
        _, now2 = strip_kst_stamp(raw_prompt)
        if now2: now_kst_str = now2

    msgs = [{"role": "system", "content": system_prompt_for(space)}]

    if sum_text:
        msgs.append({"role": "system", "content": "Conversation summary (facts only):\n" + sum_text})
    if now_kst_str:
        msgs.append({"role": "system", "content": f"Current datetime (KST): {now_kst_str}. Use this as 'now'."})
    if hist:
        budget, used = 8000-1000, 0  # 보수적 입력 예산
        tail = []
        for it in reversed(hist):
            t = approx_tokens(it["text"])
            if used + t > budget: break
            tail.append(it); used += t
        for it in reversed(tail):
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

@app.post("/api/<space>/summarize")
def summarize_hidden(space):
    """
    롤링 요약: 이전 summary + 신규 hidden 전부를 더 짧게 압축.
    body: { items:[{role,text,ts}...], prev_summary?:str, lang?:'ko'|'en', max_chars?:int }
    """
    data = request.get_json(silent=True) or {}
    items = data.get("items") or []
    prev = (data.get("prev_summary") or "").strip()
    lang = (data.get("lang") or "ko").lower()
    max_chars = int(data.get("max_chars") or 1200)

    if not isinstance(items, list):
        return jsonify({"ok": False, "error": "bad items"}), 400

    lines = []
    for it in items:
        role = "ASSISTANT" if it.get("role") == "assistant" else "USER"
        text = (it.get("text") or "").strip()
        if text:
            lines.append(f"{role}: {text}")

    if not prev and not lines:
        return jsonify({"ok": False, "error": "empty input"}), 400

    if lang.startswith("ko"):
        sys += f" 출력은 한국어. 사실/결정/요구사항/제약/수치/날짜만 남기고 {max_chars}자 이내."

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

@app.post("/api/<space>/purge_hidden")
def purge_hidden(space):
    """요약이 아닌 hidden 항목 전부 삭제."""
    k = key_for(space)
    raw = r.lrange(k, 0, -1)
    kept, removed = [], 0
    for s in raw:
        try:
            it = json.loads(s)
        except Exception:
            kept.append(s); continue
        if bool(it.get("hidden", False)) and it.get("kind") != SUMMARY_KIND:
            removed += 1; continue
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

# ===== /api/* 는 항상 JSON 에러 반환 =====
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
