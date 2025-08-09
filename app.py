# app.py
import os
#import json
import logging
#import requests
from flask import (Flask, jsonify)
                   #request, abort)

import psycopg2

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

def init_db():
    db_url = os.getenv("DATABASE_URL")  # 함수 안에서 불러오기
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as cur:
            with open(schema_path, "r", encoding="utf-8") as f:
                cur.execute(f.read())
        conn.commit()
    print("✅ DB schema ensured")

# --- 앱 시작 시 한 번만 실행 ---
if os.environ.get("RUN_MAIN") == "true":  # Flask reloader 때문에 2번 실행 방지
    try:
        init_db()
    except Exception as err:
        print(f"⚠️ DB init failed: {err}")

@app.route("/")
def home():
    return "Monday server running"
# === 라우트 ===
@app.get("/")
def root():
    return {"ok": True, "service": "monday-notion-webhook"}

@app.get("/health")
def health():
    return {"ok": True}

@app.route("/dbtest")
def db_test():
    try:
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        cur = conn.cursor()
        cur.execute("SELECT NOW();")
        now = cur.fetchone()[0]
        cur.close(); conn.close()
        return jsonify({"db_connection":"ok","time":str(now)})
    except Exception as e:
        return jsonify({"db_connection":"fail","error":str(e)}), 500
