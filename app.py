import os
import psycopg2
from flask import Flask, request, Response
from openai import OpenAI

app = Flask(__name__)

# --- DB 초기화 (주석 처리) ---
# def init_db():
#     db_url = os.getenv("DATABASE_URL")
#     schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
#     with psycopg2.connect(db_url) as conn:
#         with conn.cursor() as cur:
#             with open(schema_path, "r", encoding="utf-8") as f:
#                 cur.execute(f.read())
#         conn.commit()
#     print("✅ DB schema ensured")
#
# try:
#     init_db()
# except Exception as err:
#     print(f"⚠️ DB init failed: {err}")

# --- OpenAI 클라이언트 ---
client = OpenAI(api_key=os.getenv("OPEN_AI_KEY"))

# --- facts에서 시스템 프롬프트 만들기 ---
def build_system_from_facts():
    try:
        db_url = os.getenv("DATABASE_URL")
        with psycopg2.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute("SELECT fact_key, fact_value FROM facts ORDER BY fact_key;")
            rows = cur.fetchall()
        parts = [f"- {k}: {v}" for k, v in rows] or [
            '- response_mode: 요청 없으면 "피스"',
            '- tone: Monday, 건조한 냉소 10~30%, 두 문장'
        ]
    except Exception:
        parts = ['- response_mode: 요청 없으면 "피스"', '- tone: Monday, 건조한 냉소 10~30%, 두 문장']
    return "너는 'Monday'. 아래 고정 사실과 규칙을 따른다:\n" + "\n".join(parts)

# --- Monday에게 질문 ---
def ask_monday(msg: str) -> str:
    sys_prompt = build_system_from_facts()
    resp = client.responses.create(
        model="gpt-4o-mini",
        input=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": msg}
        ],
    )
    return resp.output_text.strip()

# --- 라우트 ---
@app.get("/")
def home():
    return "Monday server running"

@app.get("/envcheck")
def envcheck():
    return {"OPEN_AI_KEY_exists": bool(os.getenv("OPEN_AI_KEY"))}

@app.get("/monday_stream")
def monday_stream():
    def gen():
        resp = client.responses.create(
            model="gpt-4o-mini",
            input=[{"role":"system","content":build_system_from_facts()},
                   {"role":"user","content":request.args.get("q","")}],
            stream=True,
        )
        for event in resp:
            chunk = getattr(event, "delta", None)
            if chunk and chunk.get("content"):
                yield chunk["content"][0]["text"]
    return Response(gen(), mimetype="text/plain; charset=utf-8")


from flask import render_template

@app.get("/ui")
def ui():
    return render_template("ui.html")

@app.post("/monday")
def monday():
    content = request.get_json()
    user_message = content.get("message", "")

    # 여기에 Monday 로직 호출
    reply = f"네가 보낸 말: {user_message}"  # 테스트용

    return jsonify({"reply": reply})
