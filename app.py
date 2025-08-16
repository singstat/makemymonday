import os
import json
import redis
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Redis 연결
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
r = redis.from_url(redis_url)

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
    return render_template("test.html", config=config)

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
