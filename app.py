from flask import Flask, render_template, request, jsonify
import os
import json
import redis
from openai import OpenAI

app = Flask(__name__)

# OpenAI client
OPENAI_KEY = os.getenv("OPEN_AI_KEY")
client = OpenAI(api_key=OPENAI_KEY)

# Redis 설정
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
r = redis.from_url(redis_url, decode_responses=True)

@app.route("/chat", methods=["POST"])
def chat():
    """ 클라가 맥락/메타데이터/질문을 전부 들고 와서 서버는 OpenAI API 호출만 대신 해주는 단순 프록시. """
    data = request.json
    messages = data.get("messages", [])
    model = data.get("model", "gpt-4o-mini")  # 기본 모델

    try:
        # OpenAI API 호출
        resp = client.chat.completions.create(
            model=model,
            messages=messages
        )
        answer = resp.choices[0].message.content
        return jsonify({"answer": answer})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/backup", methods=["POST"])
def backup():
    data = request.json
    username = data.get("username", "unknown")
    ai_label = data.get("ai_label", "test_ai")
    history = data.get("history", [])

    redis_key = f"{username}:{ai_label}"
    r.set(redis_key, json.dumps(history, ensure_ascii=False))

    return jsonify({"status": "ok"})

# 요약 요청 처리 (추가된 부분)
@app.route("/summarize", methods=["POST"])
def summarize():
    data = request.json
    messages = data.get("messages", [])

    # 요약 처리 로직 (OpenAI API를 통해 요약 요청) 예시
    try:
        summary_prompt = "Please summarize the following conversation:\n"
        for msg in messages:
            summary_prompt += f"{msg['role']}: {msg['content']}\n"  # 대화 내용을 조합

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": summary_prompt}]
        )
        summary = resp.choices[0].message.content.strip()
        return jsonify({"summary": summary})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/<username>")
def user_page(username):
    ai_label = os.getenv("AI_LABEL", "test_ai")

    # Redis 키
    redis_key = f"{username}:{ai_label}"
    redis_summary_key = f"{username}:{ai_label}:summary"
    redis_system_key = f"{username}:{ai_label}:system"

    # Redis에서 읽기
    history_json = r.get(redis_key)
    history = json.loads(history_json) if history_json else []

    summary = r.get(redis_summary_key) or ""
    system_prompt = r.get(redis_system_key) or "You are a helpful assistant."

    # 클라에 내려줄 모든 정보
    config = {
        "ai_label": ai_label,
        "username": username,
        "history": history,
        "summary": summary,
        "system_prompt": system_prompt
    }

    template_name = "test.html" if username == "test" else "ui.html"
    return render_template(template_name, config=config)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))