# app.py — 최소 동작 버전 (session start/end + monday + ui)
import os, time, uuid, json
from flask import Flask, request, jsonify, Response

# 선택 의존성(없어도 동작하게)
try:
    import psycopg2
except Exception:
    psycopg2 = None

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

app = Flask(__name__)

SESSIONS = {}  # {sid: {"created":ts,"last":ts,"facts":[...],"messages":[(...),...]}}

# --- 옵션: DB facts 로딩 (없으면 빈 리스트) ---
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

# --- 옵션: OpenAI 호출 (키/라이브러리 없으면 에코로 대체) ---
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
    # fallback
    return f"(echo) {msg}"

# --- 라우트들 ---
@app.get("/")
def home():
    return "Monday minimal server"

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

@app.route("/monday", methods=["GET","POST"])
def monday():
    # 세션 ID
    sid = request.args.get("sid") or (request.get_json(silent=True) or {}).get("sid")
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        q = (data.get("message") or "").strip()
    else:
        q = (request.args.get("q") or "").strip()
    if not q:
        q = "상태 체크. 불필요한 말 없이 한 문장."

    facts = SESSIONS.get(sid, {}).get("facts", [])
    reply = ask_monday(q, facts)

    # 세션에 대화 저장
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
    # 여기서 요약/팩트 업데이트 넣으면 확장 가능 (지금은 최소 동작)
    return jsonify({"ok": True, "messages": len(sess["messages"]), "facts": len(sess["facts"])})

# --- 초간단 UI ---
@app.get("/ui")
def ui():
    return render_template("ui.html")