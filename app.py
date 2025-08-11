# app.py
from flask import Flask, render_template, request, jsonify

app = Flask(__name__, template_folder="templates", static_folder="static")

@app.route("/")
def home():
    # templates/ui.html 을 렌더링
    return render_template("ui.html")

@app.post("/api/echo")
def echo():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "empty"}), 400
    return jsonify({"ok": True, "text": text})

# Railway/헬스체크 대비(선택)
@app.get("/health")
def health():
    return {"ok": True}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
