from flask import Flask, render_template, request, jsonify
import os, json, redis
from openai import OpenAI

app = Flask(__name__)

# OpenAI client
OPENAI_KEY = os.getenv("OPEN_AI_KEY")
client = OpenAI(api_key=OPENAI_KEY)

import os, redis

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
r = redis.from_url(redis_url, decode_responses=True)


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

@app.route("/backup", methods=["POST"])
def backup():
    data = request.json
    username = data.get("username", "unknown")
    ai_label = data.get("ai_label", "test_ai")
    history = data.get("history", [])

    redis_key = f"{username}:{ai_label}"

    # ✅ payload 대신 history 직렬화
    r.set(redis_key, json.dumps(history, ensure_ascii=False))

    return jsonify({"status": "ok"})


@app.route("/chat", methods=["POST"])
def chat():
    """ 클라가 맥락/메타데이터/질문을 전부 들고 와서 서버는 OpenAI API 호출만 대신 해주는 단순 프록시. """
    data = request.json
    messages = data.get("messages", [])
    model = data.get("model", "gpt-4o-mini")  # 기본 모델
    system_prompt = data.get("systemPrompt", "")  # 시스템 프롬프트 받기

    # OpenAI API 호출 시 시스템 프롬프트 사용
    try:
        # 시스템 프롬프트와 기존 메시지를 합쳐서 전달
        complete_messages = [{"role": "system", "content": system_prompt}] + messages

        resp = client.chat.completions.create(
            model=model,
            messages=complete_messages
        )
        answer = resp.choices[0].message.content
        return jsonify({"answer": answer})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
