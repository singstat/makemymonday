# --- 세션/DB 헬퍼 ---
import time, uuid, os, psycopg2
from flask import request, jsonify

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
