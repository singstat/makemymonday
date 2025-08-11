# app.py
import os, json, uuid, time
from flask import Flask, render_template, request, jsonify, make_response
import redis

app = Flask(__name__, template_folder="templates", static_folder="static")
app.url_map.strict_slashes = False

REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    raise RuntimeError("환경변수 REDIS_URL 이 필요합니다. (예: redis://default:pass@host:port)")
r = redis.Redis.from_url(REDIS_URL, decode_responses=True)

MAX_ITEMS = 1000
TTL_SECONDS = 60*60*24*30  # 30일

def key_for(sid: str) -> str:
    return f"msgs:{sid}"

@app.get("/")
def home():
    sid = request.cookies.get("sid") or uuid.uuid4().hex
    resp = make_response(render_template("ui.html"))
    resp.set_cookie("sid", sid, max_age=TTL_SECONDS, samesite="Lax")
    return resp

@app.get("/api/messages")
def list_messages():
    sid = request.args.get("sid") or request.cookies.get("sid")
    if not sid:
        return jsonify({"ok": False, "error": "no sid"}), 400
    k = key_for(sid)
    items = r.lrange(k, 0, -1)
    out = []
    for s in items:
        try:
            out.append(json.loads(s))
        except Exception:
            pass
    return jsonify({"ok": True, "items": out})

@app.post("/api/messages")
def save_messages_batch():
    # sendBeacon 대응: text/plain로 올 수도 있어서 수동 파싱 보강
    data = request.get_json(silent=True)
    if data is None:
        try:
            data = json.loads(request.data.decode("utf-8"))
        except Exception:
            return jsonify({"ok": False, "error": "bad json"}), 400

    sid = data.get("sid") or request.cookies.get("sid")
    items = data.get("items")
    if not sid or not isinstance(items, list):
        return jsonify({"ok": True, "saved": 0})

    now = int(time.time()*1000)
    payloads = []
    for it in items:
        text = (it.get("text") or "").strip()
        if not text:
            continue
        ts = int(it.get("ts") or now)
        payloads.append(json.dumps({"text": text, "ts": ts}))
    if not payloads:
        return jsonify({"ok": True, "saved": 0})

    k = key_for(sid)
    with r.pipeline() as p:
        p.rpush(k, *payloads)
        p.ltrim(k, -MAX_ITEMS, -1)  # 마지막 MAX_ITEMS개만 유지
        p.expire(k, TTL_SECONDS)
        p.execute()
    return jsonify({"ok": True, "saved": len(payloads)})

@app.get("/health")
def health():
    try:
        r.ping()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500

if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
