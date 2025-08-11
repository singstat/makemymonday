# app.py
import os
import json
import uuid
import time
import re
from datetime import datetime, timezone, timedelta

from flask import Flask, render_template, request, jsonify, make_response
import redis
from openai import OpenAI

# -------------------------
# Config & Clients
# -------------------------
app = Flask(__name__, template_folder="templates", static_folder="static")
app.url_map.strict_slashes = False

REDIS_URL = os.getenv("REDIS_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_KEY")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL 환경변수가 필요합니다.")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY 또는 OPEN_AI_KEY 환경변수가 필요합니다.")

r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
oa = OpenAI(api_key=OPENAI_API_KEY)

MAX_ITEMS = 1000                  # 사용자별 최대 저장 개수
TTL_SECONDS = 60 * 60 * 24 * 30   # 30일
KST = timezone(timedelta(hours=9))
STAMP_RE = re.compile(r"\b(\d{4})\s(\d{2})\s(\d{2})\s(\d{2})\s(\d{2})\s*$")

def key_for(sid: str) -> str:
    return f"msgs:{sid}"

# -------------------------
# Helpers
# -------------------------
def _normalize_history(history):
    """클라에서 온 history를 안전하게 정규화"""
    out = []
    for it in history or []:
        role = "assistant" if (it.get("role") == "assistant") else "user"
        text = str(it.get("text") or "")
        try:
            ts =
