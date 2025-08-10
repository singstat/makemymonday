# --- 세션/DB 헬퍼 ---
import time, uuid, os, psycopg2
from flask import request, jsonify,Flask

app = Flask(__name__)

SESSIONS = {}  # {sid: {"created":ts,"last":ts,"facts":[...],"messages":[(...),...]}}
DB_URL = os.getenv("DATABASE_URL")

def load_facts_from_db() -> list[str]:
    """facts 테이블 → ['key=value', ...] 리스트로 변환"""
    try:
        with psycopg2.connect(DB_URL) as conn, conn.cursor() as cur:
            cur.execute("SELECT fact_key, fact_value FROM facts ORDER BY fact_key;")
            rows = cur.fetchall()
        return [f"{k}={v}" for k, v in rows]  # 없으면 빈 리스트
    except Exception as _:
        return []

@app.get("/")
def home():
    return "Monday server running"

@app.get("/ui")
def ui():
    return render_template("ui.html")

@app.route("/monday", methods=["GET", "POST"])
def monday():
    # sid 체크
    sid = request.args.get("sid") or (request.get_json(silent=True) or {}).get("sid")
    if sid in SESSIONS:
        SESSIONS[sid]["last"] = time.time()

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        q = (data.get("message") or "").strip()
    else:
        q = (request.args.get("q") or "").strip()

    if not q:
        q = "상태 체크. 불필요한 말 없이 한 문장."

    # 대화 기록 저장
    if sid in SESSIONS:
        SESSIONS[sid]["messages"].append(("user", q))

    # 실제 Monday 호출 (임시로 에코)
    reply = f"네가 보낸 말: {q}"

    if sid in SESSIONS:
        SESSIONS[sid]["messages"].append(("monday", reply))

    return reply


@app.post("/session/start")
def session_start():
    # 클라이언트가 추가로 보내온 임시 세션 팩트(선택)
    extra = []
    if request.is_json:
        extra = (request.json.get("facts") or [])
        # 문자열만 허용, key=value 형태 권장
        extra = [str(x) for x in extra if x]

    base = load_facts_from_db()  # DB에서 항상 시도
    facts = base + extra         # DB 기반 + 추가 덧붙이기

    sid = uuid.uuid4().hex
    now = time.time()
    SESSIONS[sid] = {"created": now, "last": now, "facts": facts, "messages": []}
    return jsonify({"session_id": sid, "facts_count": len(facts)})

# 참고: /monday에서 SESSIONS[sid]["messages"]에 대화 계속 append 하는 건 기존 그대로.
