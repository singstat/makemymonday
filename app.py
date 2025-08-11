# app.py
from flask import Flask, render_template, request, jsonify

app = Flask(__name__, template_folder="templates", static_folder="static")
app.url_map.strict_slashes = False  # /api/echo 와 /api/echo/ 둘 다 허용

@app.route("/")
def home():
    return render_template("ui.html")

@app.route("/api/echo", methods=["GET", "POST"])
def echo():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
    else:  # GET 지원 (테스트/브라우저 호출용)
        text = (request.args.get("text") or "").strip()

    if not text:
        return jsonify({"ok": False, "error": "empty"}), 400
    return jsonify({"ok": True, "text": text})

@app.get("/health")
def health():
    return {"ok": True}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
