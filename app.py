import os
import redis
from flask import Flask, render_template

app = Flask(__name__)

# Redis 연결 (지금은 안 써도 무방)
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
r = redis.from_url(redis_url)

@app.route("/test")
def test():
    config = {
        "space": os.getenv("SPACE_NAME", "default-space"),
        "ai_label": os.getenv("AI_LABEL", "AI")
    }
    return render_template("test.html", config=config)

@app.route("/<username>")
def user_page(username):
    config = {
        "space": "default-space",
        "ai_label": "AI",
        "username": username
    }
    return render_template("test.html", config=config)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
