# app.py

#import json
import logging
import request


from flask import Flask, request, Response, jsonify
from openai import OpenAI
import os, psycopg2

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

def init_db():
    db_url = os.getenv("DATABASE_URL")
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as cur:
            with open(schema_path, "r", encoding="utf-8") as f:
                cur.execute(f.read())
        conn.commit()
    print("✅ DB schema ensured")

# 🔧 gunicorn 환경에서도 실행되도록: 모듈 로드 시 바로 돌림 (중복 안전)
#try:
#    init_db()
#except Exception as err:
#    print(f"⚠️ DB init failed: {err}")

@app.route("/dbtest")
def db_test():
    try:
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        cur = conn.cursor()
        cur.execute("SELECT NOW();")
        now = cur.fetchone()[0]
        cur.close(); conn.close()
        return jsonify({"db_connection":"ok","time":str(now)})
    except Exception as e:
        return jsonify({"db_connection":"fail","error":str(e)}), 500



@app.route("/")
def home():
    return "Monday server running"
# === 라우트 ===
@app.get("/")
def root():
    return {"ok": True, "service": "monday-notion-webhook"}

@app.get("/health")
def health():
    return {"ok": True}


client = OpenAI(api_key=os.getenv("OPEN_AI_KEY"))

@app.get("/envcheck")
def envcheck():
    return {"OPEN_AI_KEY_exists": bool(os.getenv("OPEN_AI_KEY"))}


def build_system_from_facts():
    try:
        db_url = os.getenv("DATABASE_URL")
        with psycopg2.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute("SELECT fact_key, fact_value FROM facts ORDER BY fact_key;")
            rows = cur.fetchall()
        parts = [f"- {k}: {v}" for k,v in rows] or [
            '- response_mode: 요청 없으면 "피스"',
            '- tone: Monday, 건조한 냉소 10~30%, 두 문장',
        ]
    except Exception:
        parts = ['- response_mode: 요청 없으면 "피스"', '- tone: Monday, 건조한 냉소 10~30%, 두 문장']
    return "너는 'Monday'. 아래 고정 사실과 규칙을 따른다:\n" + "\n".join(parts)

def ask_monday(msg: str) -> str:
    sys_prompt = build_system_from_facts()
    resp = client.responses.create(
        model="gpt-4o-mini",
        input=[
            {"role":"system","content":sys_prompt},
            {"role":"user","content":msg}
        ],
    )
    return resp.output_text.strip()

@app.get("/monday")
def talk_to_monday():
    q = request.args.get("q", "상태 체크. 불필요한 말 없이 한 문장.")
    reply = ask_monday(q)
    return Response(reply, mimetype="text/plain; charset=utf-8")

