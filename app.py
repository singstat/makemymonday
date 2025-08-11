# app.py
from flask import Flask, render_template

app = Flask(__name__, template_folder="templates", static_folder="static")
app.url_map.strict_slashes = False

@app.get("/")
def ui():
    return render_template("ui.html")  # templates/ui.html

# (선택) 헬스체크
@app.get("/health")
def health():
    return {"ok": True}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
