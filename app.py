import uuid, time
from flask import request, jsonify

SESSIONS = {}  # {sid: {"created": ts, "last": ts}}

@app.post("/session/start")
def session_start():
    sid = uuid.uuid4().hex
    now = time.time()
    SESSIONS[sid] = {"created": now, "last": now}
    return jsonify({"session_id": sid})

@app.post("/session/end")
def session_end():
    data = request.get_json(silent=True) or {}
    sid = data.get("session_id")
    if sid: SESSIONS.pop(sid, None)
    return jsonify({"ok": True})

@app.post("/session/ping")  # 선택: 가끔 살아있다고 알려주기
def session_ping():
    data = request.get_json(silent=True) or {}
    sid = data.get("session_id")
    if sid in SESSIONS:
        SESSIONS[sid]["last"] = time.time()
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 404

# /monday에서 세션 태그만 기록(선택)
@app.route("/monday", methods=["GET","POST"])
def monday():
    sid = request.args.get("sid") or (request.get_json(silent=True) or {}).get("sid")
    if sid in SESSIONS: SESSIONS[sid]["last"] = time.time()
    # ... 기존 ask_monday 로직 ...
