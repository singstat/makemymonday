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

MAX_ITEMS = 1000      # 사용자별 최대 저장 개수
TTL_SECONDS = 60*60*24*30  # 30일 보관

def key_for(sid: str) -> str:
    return f"msgs:{sid}"

@app.get("/")
def home():
    sid = request.cookies.get("sid") or uuid.uuid4().hex
    resp = make_response(render_template("ui.html"))  # templates/ui.html
    resp.set_cookie("sid", sid, max_age=TTL_SECONDS, samesite="Lax")
    return resp

@app.get("/api/messages")
def list_messages():
    sid = request.args.get("sid") or request.cookies.get("sid")
    if not sid:
        return jsonify({"ok": False, "error": "no sid"}), 400
    k = key_for(sid)
    items = r.lrange(k, 0, -1)  # 문자열 리스트
    # 저장은 JSON 문자열로 하므로 파싱
    out = []
    for s in items:
        try:
            out.append(json.loads(s))
        except Exception:
            pass
    return jsonify({"ok": True, "items": out})

@app.post("/api/message")
def add_message():
    data = request.get_json(silent=True) or {}
    sid = request.cookies.get("sid") or data.get("sid")
    text = (data.get("text") or "").strip()
    if not sid or not text:
        return jsonify({"ok": False, "error": "bad payload"}), 400

    k = key_for(sid)
    item = json.dumps({"text": text, "ts": int(time.time()*1000)})
    # 리스트에 push, 길이 제한, TTL 갱신
    with r.pipeline() as p:
        p.rpush(k, item)
        p.ltrim(k, max(-MAX_ITEMS, -MAX_ITEMS), -1)  # 뒤에서 MAX_ITEMS 개만 유지
        p.expire(k, TTL_SECONDS)
        p.execute()
    return jsonify({"ok": True})
