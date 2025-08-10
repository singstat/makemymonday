import os, time, uuid
from flask import Flask, request, jsonify, Response, render_template

# 템플릿/정적 경로 명시 (경로 꼬임 방지)
app = Flask(__name__, template_folder="templates", static_folder="static")
# 맨 위 import 옆에 추가
import traceback, logging
logging.basicConfig(level=logging.INFO)
app.config.update(DEBUG=True, PROPAGATE_EXCEPTIONS=True)

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
    extra = []
    if request.is_json:
        extra = [str(x) for x in (request.json.get("facts") or []) if x]
    facts = load_facts_from_db() + extra
    sid = uuid.uuid4().hex
    now = time.time()
    SESSIONS[sid] = {"created": now, "last": now, "facts": facts, "messages": []}
    return jsonify({"session_id": sid, "facts_count": len(facts)})

from datetime import datetime

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

    # 오늘 날짜 (서버 시간)
    today_str = datetime.now().strftime("%Y-%m-%d (%A)")

    # facts에 오늘 날짜 추가
    facts = SESSIONS.get(sid, {}).get("facts", [])
    facts = facts + [f"오늘 날짜는 {today_str}"]

    reply = ask_monday(q, facts)

    if sid in SESSIONS:
        SESSIONS[sid]["last"] = time.time()
        SESSIONS[sid]["messages"].append(("user", q))
        SESSIONS[sid]["messages"].append(("monday", reply))

    return Response(reply, mimetype="text/plain; charset=utf-8")


@app.post("/session/end")
def session_end():
    data = request.get_json(silent=True) or {}
    sid = data.get("session_id")
    sess = SESSIONS.pop(sid, None)
    if not sess:
        return jsonify({"ok": False, "error":"no such session"}), 404
    return jsonify({"ok": True, "messages": len(sess["messages"]), "facts": len(sess["facts"])})
