import os
import redis
from flask import Flask, render_template, request

app = Flask(__name__)

# Railway에서는 REDIS_URL 환경변수가 자동으로 주어집니다.
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
r = redis.from_url(redis_url)

@app.route("/test", methods=["GET"])
def index():
    return render_template("test.html", config=config)

@app.route("/count", methods=["POST"])
def count():
    # Redis 카운터 증가
    count = r.incr("page_count")
    return render_template("index.html", count=count)

if __name__ == "__main__":
    # Railway 기본 포트는 $PORT 환경변수에 담김
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
