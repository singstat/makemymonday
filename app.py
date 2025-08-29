# app.py
import os
from flask import Flask, render_template

app = Flask(__name__, static_folder="static", template_folder="templates")

@app.route("/health")
def health():
    return "ok", 200

@app.route("/test")
def test_page():
    # templates/test.html 을 렌더링
    return render_template("test.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))  # Railway는 PORT 환경변수를 설정함
    app.run(host="0.0.0.0", port=port)
