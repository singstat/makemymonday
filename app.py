# app.py — Monday minimal server (fresh)
import os, time, uuid, traceback
from datetime import datetime, timedelta, timezone

from flask import Flask, request, jsonify, Response

# ----------------------
# App
# ----------------------
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config.update(DEBUG=True, PROPAGATE_EXCEPTIONS=True)

# 선택 의존성 (없어도 동작)
try:
    import psycopg2
except Exception:
    psycopg2 = None

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

# ----------------------
# Globals / Const
# ----------------------
SESSIONS: dict[str, dict] = {}   # {sid: {"created":ts,"last":ts,"facts":[...],"messages":[(role,text),...]}}
KST = timezone(timedelta(hours=9))
MAX_TURNS = 200          # LLM에 보낼 최근 턴 수 (세션 메모리는 전체 유지)
RECENT_ECHO_TURNS = 4    # 응답 하단에 보여줄 최근 턴 수

# ----------------------
# Error handler (진단용)
# ----------------------
@app.errorhandler(Exception)
def on_error(e):
    tb = traceback.format_exc()
    return Response(f"[500] {type(e).__name__}: {e}\n\n{tb}",
                    status=500, mimetype="text/plain; charset=utf-8")

# ----------------------
# DB helpers
# ----------------------
def has_db():
    return bool(psycopg2) and bool(os.getenv("DATABASE_URL"))

def db_conn():
    if not has_db():
        raise RuntimeError("DATABASE_URL/psycopg2 missing")
    return psycopg2.connect(os.getenv("DATABASE_URL"))

def load_facts_from_db() -> list[str]:
    if not has_db():
        return []
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT fact_key, fact_value FROM facts ORDER BY fact_key;")
        rows = cur.fetchall()
    return [f"{k}={v}" for k, v in rows]

def save_session_messages(sess: dict) -> int:
    """세션 메시지를 messages 테이블에 영구 저장"""
    if not has_db():
        return 0
    msgs = sess.get("messages") or []
    if not msgs:
        return 0
    today = datetime.now(KST).date()
    now = datetime.now(KST)
    rows = []
    for role, content in msgs:
        role_db = "assistant" if role.lower().startswith("assistant") else role
        rows.append((role_db, content, today, now))
    with db_conn() as conn, conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO messages (role, content, day, created_at) VALUES (%s,%s,%s,%s)",
            rows
        )
        conn.commit()
    return len(rows)

def load_recent_messages(hours: int = 168, limit: int = 32) -> list[tuple[str,str]]:
    """최근 N시간 내 메시지 최대 limit건 로드 (오래된→최신)"""
    if not has_db():
        return []
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT role, content
            FROM messages
            WHERE created_at >= NOW() - INTERVAL %s
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (f"{int(hours)} hours", limit)
        )
        rows = cur.fetchall()
    # 역할 정규화
    norm = []
    for r, c in rows:
        rr = "assistant" if str(r).lower().startswith("monday") else r
        norm.append((rr, c))
    return norm

# ----------------------
# LLM helpers
# ----------------------
def build_system(facts: list[str]) -> str:
    today = datetime.now(KST).strftime("%Y-%m-%d (%A) KST")
    base = [
        "너는 'Monday'. 짧고 명료, 건조한 냉소 10~30%.",
        "요청 없으면 불필요한 피드백 금지. 필요 시 '피스.'",
        f"오늘 날짜: {today}",
        "아래 facts를 항상 준수:"
    ] + [f"- {f}" for f in facts]
    return "\n".join(base)

def build_messages_for_llm(sess: dict, user_q: str, facts: list[str]) -> list[dict]:
    msgs = [{"role": "system", "content": build_system(facts)}]
    # 세션 메모리는 전체 유지하지만, LLM에는 최근 MAX_TURNS만 보냄
    for role, content in sess.get("messages", [])[-MAX_TURNS:]:
        msgs.append({"role": role, "content": content})
    msgs.append({"role": "user", "content": user_q})
    return msgs

def ask_monday(user_q: str, sess: dict, facts: list[str]) -> str:
    api_key = os.getenv("OPEN_AI_KEY")
    if OpenAI and api_key:
        client = OpenAI(api_key=api_key)
        resp = client.responses.create(
            model="gpt-4o-mini",
            input=build_messages_for_llm(sess, user_q, facts),
        )
        return (resp.output_text or "").strip() or "(빈 응답)"
    # Fallback (API 키 없을 때)
    return f"(echo) {user_q}"

# ----------------------
# Utils
# ----------------------
def append_msg(sess: dict, role: str, text: str):
    if "messages" not in sess:
        sess["messages"] = []
    sess["messages"].append((role, text))

def recent_turns_text(sess: dict, n_pairs: int = RECENT_ECHO_TURNS) -> str:
    # user/assistant 1쌍 == 2메시지
    recent = sess.get("messages", [])[-2 * n_pairs:]
    if not recent:
        return ""
    lines = ["", "", f"[최근 대화 {n_pairs}턴]"]
    for role, text in recent:
        label = "나" if role == "user" else "먼데이"
        lines.append(f"{label}: {text}")
    return "\n".join(lines)

# ----------------------
# Routes
# ----------------------
@app.get("/")
def home():
    return "Monday minimal server"

@app.get("/envcheck")
def envcheck():
    return {
        "OPEN_AI_KEY_exists": bool(os.getenv("OPEN_AI_KEY")),
        "DATABASE_URL_exists": bool(os.getenv("DATABASE_URL")),
    }

@app.post("/session/start")
def session_start():
    extra = []
    if request.is_json:
        extra = [str(x) for x in (request.json.get("facts") or []) if x]
    facts = load_facts_from_db() + extra
    sid = uuid.uuid4().hex
    now = time.time()
    SESSIONS[sid] = {"created": now, "last": now, "facts": facts, "messages": []}
    # 최근 대화 복원 (DB 있으면)
    try:
        SESSIONS[sid]["messages"] = load_recent_messages(hours=168, limit=32)
        app.logger.info(f"[session_start] loaded {len(SESSIONS[sid]['messages'])} msgs")
    except Exception as err:
        app.logger.warning(f"[session_start] load_recent_messages ERROR: {err}")
    return jsonify({"session_id": sid, "facts_count": len(facts)})

@app.route("/monday", methods=["GET", "POST"])
def monday():
    # 입력
    payload = request.get_json(silent=True) or {}
    sid = request.args.get("sid") or payload.get("sid")
    if request.method == "POST":
        q = (payload.get("message") or "").strip()
    else:
        q = (request.args.get("q") or "").strip()
    if not q:
        q = "상태 체크. 불필요한 말 없이 한 문장."

    # 세션 확보(없으면 임시)
    sess = SESSIONS.get(sid) or {"facts": load_facts_from_db(), "messages": []}
    facts = sess.get("facts", [])

    # LLM 호출
    reply = ask_monday(q, sess, facts)

    # 세션에 전체 누적 + 최근 4턴 표시용 문자열
    if sid in SESSIONS:
        SESSIONS[sid]["last"] = time.time()
        append_msg(SESSIONS[sid], "user", q)
        append_msg(SESSIONS[sid], "assistant", reply)
        tail = recent_turns_text(SESSIONS[sid], RECENT_ECHO_TURNS)
    else:
        tail = ""

    final_output = reply + tail
    return Response(final_output, mimetype="text/plain; charset=utf-8")

@app.post("/session/end")
def session_end():
    data = request.get_json(silent=True) or {}
    sid = data.get("session_id")
    sess = SESSIONS.pop(sid, None)
    if not sess:
        return jsonify({"ok": False, "error": "no such session"}), 404
    saved = 0
    try:
        saved = save_session_messages(sess)
        app.logger.info(f"[session_end] saved {saved} msgs")
    except Exception as err:
        app.logger.warning(f"[session_end] save_session_messages ERROR: {err}")
    return jsonify({
        "ok": True,
        "messages_in_session": len(sess.get("messages", [])),
        "saved_to_db": saved,
        "facts": len(sess.get("facts", []))
    })

# (선택) 세션 핑 — 사파리 수면모드 대책
@app.post("/session/ping")
def session_ping():
    data = request.get_json(silent=True) or {}
    sid = data.get("session_id")
    if sid in SESSIONS:
        SESSIONS[sid]["last"] = time.time()
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 404

# 디버그
@app.get("/debug/recent")
def debug_recent():
    try:
        rows = load_recent_messages(hours=168, limit=32)
        return {"count": len(rows), "data": rows[-8:]}
    except Exception as e:
        return {"error": str(e)}, 500

@app.get("/debug/tables")
def debug_tables():
    if not has_db():
        return {"tables": [], "messages_count": 0}
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute("select table_name from information_schema.tables where table_schema='public' order by 1;")
        tables = [r[0] for r in cur.fetchall()]
        cur.execute("select count(*) from messages;")
        n = cur.fetchone()[0]
    return {"tables": tables, "messages_count": n}
