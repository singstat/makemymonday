import os
import json
import redis
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Redis 연결
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
r = redis.from_url(redis_url)

from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPEN_AI_KEY"))

import tiktoken

@app.route("/token_count", methods=["POST"])
def token_count():
    data = request.json
    history = data.get("history", [])
    username = data.get("username")

    # system prompt 결정
    if username == "test":
        system_prompt = (
            "Provide one action item at a time, do not suggest unnecessary implementations, "
            "and implement only the functionality I specify exactly."
        )
    else:
        system_prompt = ""  # monday 기본값

    enc = tiktoken.encoding_for_model("gpt-4o-mini")

    tokens = 0
    # system 메시지 포함
    tokens += len(enc.encode(system_prompt))

    # 히스토리 메시지 포함
    for msg in history:
        tokens += len(enc.encode(msg))

    return jsonify({"token_count": tokens})


@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    username = data.get("username")
    text = data.get("text", "")

    # ai_label 분기
    if username == "test":
        ai_label = "test_ai"
        system_prompt = (
            "Provide one action item at a time, do not suggest unnecessary implementations, "
            "and implement only the functionality I specify exactly."
        )
    else:
        ai_label = "monday"
        system_prompt = ""  # 나중에 넣을 지침

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]
    )

    ai_msg = resp.choices[0].message.content

    return jsonify({"ai_message": f"{ai_label}: {ai_msg}"})

@app.route("/<username>")
def user_page(username):
    ai_label = os.getenv("AI_LABEL", "test_ai")
    redis_key = f"{username}:{ai_label}"

    # Redis에서 이전 대화 불러오기
    raw = r.get(redis_key)
    history = json.loads(raw) if raw else []

    config = {
        "ai_label": ai_label,
        "username": username,
        "history": history
    }

    # test 사용자일 때 test.html, 아니면 UI.html을 반환
    template_name = "test.html" if username == "test" else "UI.html"
    return render_template(template_name, config=config)

@app.route("/backup", methods=["POST"])
def backup():
    data = request.json
    username = data.get("username")
    ai_label = data.get("ai_label", "test_ai")
    history = data.get("history", [])

    redis_key = f"{username}:{ai_label}"

    # JSON으로 통째로 저장
    r.set(redis_key, json.dumps(history, ensure_ascii=False))

    return jsonify({"status": "ok", "count": len(history)})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
