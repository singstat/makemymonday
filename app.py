import os
import redis
from flask import Flask, render_template

app = Flask(__name__)

# Redis 연결 (지금은 쓰지 않아도 됨)
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
r = redis.from_url(redis_url)

@app.route("/<username>")
def user_page(username):
    config = {
        "ai_label": os.getenv("AI_LABEL", "test_ai"),
        "username": username
    }

    # 분기 준비 (지금은 둘 다 test.html로 반환)
    if username == "test":
        return render_template("test.html", config=config)
    else:
        # 나중에 다른 템플릿이나 처리를 붙일 수 있음
        return render_template("test.html", config=config)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
