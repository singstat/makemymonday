from flask import Flask, render_template, request, jsonify
import os, json, redis
from openai import OpenAI

app = Flask(__name__)

# OpenAI client
OPENAI_KEY = os.getenv("OPEN_AI_KEY")
client = OpenAI(api_key=OPENAI_KEY)

# Redis 연결
r = redis.Redis(host="localhost", port=6379, decode_responses=True)


@app.route("/<username>")
def user_page(username):
    """
    유저별 페이지.
    test면 test.html, 아니면 ui.html 반환.
    """
    ai_label = os.getenv("AI_LABEL", "test_ai")
    config = {
        "ai_label": ai_label,
        "username": username
    }
    template_name = "test.html" if username == "test" else "ui.html"
    return render_template(template_name, config=config)


@app.route("/chat", methods=["POST"])
def chat():
    """
    클라가 맥락/메타데이터/질문을 전부 들고 와서
    서버는 OpenAI API 호출만 대신 해주는 단순 프록시.
    """
    data = request.json
    messages = data.get("messages", [])
    model = data.get("model", "gpt-4o-mini")  # 기본 모델

    try:
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
    """
    클라가 세션 종료 시점에 전체 맥락/메타데이터를 백업.
    """
    data = request.json
    username = data.get("username")
    ai_label = data.get("ai_label", "test_ai")
    payload = data.get("payload", {})  # history, metadata 등 전체

    redis_key = f"{username}:{ai_label}"
    r.set(redis_key, json.dumps(payload, ensure_ascii=False))
    return jsonify({"status": "ok", "saved_key": redis_key})


@app.route("/restore/<username>", methods=["GET"])
def restore(username):
    """
    클라가 다시 접속할 때 Redis에서 복원.
    """
    ai_label = os.getenv("AI_LABEL", "test_ai")
    redis_key = f"{username}:{ai_label}"
    raw = r.get(redis_key)
    if raw:
        return jsonify({"payload": json.loads(raw)})
    else:
        return jsonify({"payload": {}})  # 없으면 빈 값


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
