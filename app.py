import os, time, uuid
from flask import Flask, request, jsonify, Response, render_template
import traceback, logging
from datetime import datetime, timedelta, timezone
app = Flask(__name__, template_folder="templates", static_folder="static")

logging.basicConfig(level=logging.INFO)
app.config.update(DEBUG=True, PROPAGATE_EXCEPTIONS=True)

KST = timezone(timedelta(hours=9))
MAX_TURNS = 16  # 최근 턴 유지
SUMMARIZE_AFTER = 24  # 이 턴 수 넘으면 앞부분 요약


def db_conn():
    import psycopg2, os
    url = os.getenv("DATABASE_URL")
    if not url: raise RuntimeError("DATABASE_URL missing")
    return psycopg2.connect(url)

def save_session_messages(sess):
    """SESSIONS[sid]['messages'] -> messages 테이블에 일괄 저장"""
    if not sess or not sess.get("messages"):
        return 0
    rows = []
    today = datetime.now(KST).date()
    now = datetime.now(KST)
    for role, content in sess["messages"]:
        # role은 'user' 또는 'assistant'로 저장
        role_db = 'assistant' if role.lower().startswith('monday') else role
        rows.append((role_db, content, today, now))
    with db_conn() as conn, conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO messages (role, content, day, created_at) VALUES (%s,%s,%s,%s)",
            rows
        )
        conn.commit()
    return len(rows)

def load_recent_messages(limit=16):
    """DB에서 최근 메시지 몇 개 불러와 세션에 복원 (오늘 위주, 부족하면 어제까지)"""
    with db_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT role, content FROM messages
            WHERE created_at >= NOW() - INTERVAL '36 hours'
            ORDER BY created_at ASC
            LIMIT %s
        """, (limit,))
        return [(r, c) for r, c in cur.fetchall()]

def build_system(facts:list[str])->str:
    today = datetime.now(KST).strftime("%Y-%m-%d (%A) KST")
    base = [
        "너는 'Monday'. 짧고 명료, 건조한 냉소 10~30%.",
        "요청 없으면 불필요한 피드백 금지. 필요 시 '피스.'",
        f"오늘 날짜: {today}",
        "아래 facts를 항상 준수:"
    ] + [f"- {f}" for f in facts]
    return "\n".join(base)

def need_summarize(sess)->bool:
    return len(sess["messages"]) > SUMMARIZE_AFTER

def summarize_history(client, sess):
    """앞부분 요약해서 sess['summary']에 누적하고 messages는 최근 턴만 남김"""
    hist_text = "\n".join(f"{r.upper()}: {t}" for r,t in sess["messages"][:-MAX_TURNS])
    prompt = f"다음 대화를 5줄 이내 핵심만, 사실 위주로 요약:\n{hist_text}"
    resp = client.responses.create(
        model="gpt-4o-mini",
        input=[{"role":"user","content":prompt}]
    )
    add = (resp.output_text or "").strip()
    sess["summary"] = (sess.get("summary") or "") + ("\n" if sess.get("summary") else "") + add
    # 최근 턴만 남기기
    sess["messages"] = sess["messages"][-MAX_TURNS:]

def build_messages_for_llm(sess, user_q:str, facts:list[str]):
    msgs = []
    msgs.append({"role":"system","content": build_system(facts)})
    if sess.get("summary"):
        msgs.append({"role":"system","content": "이전 대화 요약:\n"+sess["summary"]})
    # 과거 대화(최근만)
    for role, content in sess["messages"]:
        msgs.append({"role": role, "content": content})
    # 이번 사용자 입력
    msgs.append({"role":"user","content": user_q})
    return msgs

@app.errorhandler(Exception)
def on_error(e):
    # 브라우저에 스택트레이스 그대로 노출 (진단용)
    tb = traceback.format_exc()
    return Response(f"[500] {type(e).__name__}: {e}\n\n{tb}",
                    status=500, mimetype="text/plain; charset=utf-8")

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/envcheck")
def envcheck():
    return {
        "OPEN_AI_KEY_exists": bool(os.getenv("OPEN_AI_KEY")),
        "DATABASE_URL_exists": bool(os.getenv("DATABASE_URL"))
    }



# 선택 의존성(없어도 동작)
try:
    import psycopg2
except Exception:
    psycopg2 = None

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

SESSIONS = {}  # {sid: {"created":ts,"last":ts,"facts":[...],"messages":[(...),...]}}

def load_facts_from_db():
    db_url = os.getenv("DATABASE_URL")
    if not (psycopg2 and db_url):
        return []
    try:
        with psycopg2.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute("SELECT fact_key, fact_value FROM facts ORDER BY fact_key;")
            rows = cur.fetchall()
        return [f"{k}={v}" for k, v in rows]
    except Exception:
        return []

def ask_monday(msg: str, facts: list[str]) -> str:
    api_key = os.getenv("OPEN_AI_KEY")
    if OpenAI and api_key:
        try:
            client = OpenAI(api_key=api_key)
            sys = "너는 Monday. 다음 고정 팩트를 항상 참고하라:\n" + "\n".join(f"- {f}" for f in facts)
            resp = client.responses.create(
                model="gpt-4o-mini",
                input=[{"role":"system","content":sys}, {"role":"user","content":msg}],
            )
            return (resp.output_text or "").strip() or "(빈 응답)"
        except Exception as err:
            return f"[OpenAI ERROR] {err}"
    return f"(echo) {msg}"

@app.get("/")
def home():
    return "Monday minimal server"

@app.get("/ui")
def ui():
    # 여기서 템플릿 렌더 → 500이면 보통 파일 경로/이름 문제
    return render_template("ui.html")

@app.post("/session/start")
def session_start():
    # ... 기존 코드 ...
    SESSIONS[sid] = {"created": now, "last": now, "facts": facts, "messages": []}
    # 🔹 과거 대화 이어받기 (선택: 최근 16턴)
    try:
        SESSIONS[sid]["messages"] = load_recent_messages(limit=16)
    except Exception as _:
        pass
    return jsonify({"session_id": sid, "facts_count": len(facts)})


@app.route("/monday", methods=["GET","POST"])
def monday():
    sid = request.args.get("sid") or (request.get_json(silent=True) or {}).get("sid")
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        q = (data.get("message") or "").strip()
    else:
        q = (request.args.get("q") or "").strip()
    if not q:
        q = "상태 체크. 불필요한 말 없이 한 문장."

    # 세션 확보
    sess = SESSIONS.get(sid)
    if not sess:
        # 세션이 없으면 임시 세션처럼 동작
        facts = load_facts_from_db()
        sess = {"messages": [], "summary": ""}
    else:
        facts = sess.get("facts", [])

    # 길어지면 앞부분 요약
    api_key = os.getenv("OPEN_AI_KEY")
    client = OpenAI(api_key=api_key) if (OpenAI and api_key) else None
    if client and need_summarize(sess):
        summarize_history(client, sess)

    # LLM 호출(세션 로그 전부 포함)
    if client:
        llm_input = client.responses.create(
            model="gpt-4o-mini",
            input=build_messages_for_llm(sess, q, facts)
        )
        reply = (llm_input.output_text or "").strip() or "(빈 응답)"
    else:
        reply = f"(echo) {q}"

    # 세션에 기록
    if sid in SESSIONS:
        sess["last"] = time.time()
        sess["messages"].append(("user", q))
        sess["messages"].append(("assistant", reply))
        SESSIONS[sid] = sess

    return Response(reply, mimetype="text/plain; charset=utf-8")

@app.post("/session/end")
def session_end():
    data = request.get_json(silent=True) or {}
    sid = data.get("session_id")
    sess = SESSIONS.pop(sid, None)
    if not sess:
        return jsonify({"ok": False, "error":"no such session"}), 404

    saved = 0
    try:
        saved = save_session_messages(sess)
    except Exception as _:
        saved = 0

    return jsonify({"ok": True,
                    "messages_in_session": len(sess["messages"]),
                    "saved_to_db": saved,
                    "facts": len(sess["facts"])})
