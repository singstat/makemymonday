from flask import Flask, render_template, request, jsonify
import os
import json
import redis
from openai import OpenAI
from prompts import get_prompt

app = Flask(__name__)

# OpenAI client
OPENAI_KEY = os.getenv("OPEN_AI_KEY")
client = OpenAI(api_key=OPENAI_KEY)

# Redis 설정
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
r = redis.from_url(redis_url, decode_responses=True)

import tiktoken


def count_tokens(messages, model="gpt-4o-mini"):
    """메시지 배열의 토큰 수를 계산"""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")  # fallback

    total_tokens = 0
    for msg in messages:
        total_tokens += len(encoding.encode(msg.get("content", "")))
    return total_tokens


@app.route("/chat", methods=["POST"])
def chat():
    """ 클라가 맥락/메타데이터/질문을 전부 들고 와서 서버는 OpenAI API 호출만 대신 해주는 단순 프록시. """
    data = request.json
    messages = data.get("messages", [])
    model = data.get("model", "gpt-4o-mini")  # 기본 모델
    ai_label = data.get("ai_label", "default")  # 클라이언트에서 ai_label을 가져옵니다.

    # 시스템 프롬프트를 get_prompt를 사용하여 가져옵니다.
    system_prompt = get_prompt(ai_label)

    # ✅ 토큰 계산 (요청 메시지 전체 기준)
    token_count = count_tokens(messages)
    print(f"🔢 Token count = {token_count}")

    if token_count > 8192:
        # 1. 요약 및 사용자 메시지를 요약 함수에 전달
        summary = summarize_with_messages(messages, get_prompt("summary"))

        # 2. 요약 값을 업데이트
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": summary}  # 요약 추가
        ]
        clear_user_messages = True  # 클라이언트에게 사용자 메시지를 지우라는 신호
    else:
        # 토큰 수가 8192 이하일 경우 그대로 유지
        messages = [
            {"role": "system", "content": system_prompt},
            *messages
        ]
        clear_user_messages = False  # 메시지 삭제 신호 없음

    try:
        # OpenAI API 호출
        resp = client.chat.completions.create(
            model=model,
            messages=messages
        )
        answer = resp.choices[0].message.content
        return jsonify({"answer": answer, "clear_user_messages": clear_user_messages})  # 삭제 신호 추가
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def summarize_with_messages(messages, summary_prompt):
    """요약 처리"""
    if not messages:
        return ""

    full_prompt = summary_prompt + "\n"
    for msg in messages:
        full_prompt += f"{msg['role']}: {msg['content']}\n"

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": full_prompt}]
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error summarizing messages: {str(e)}")
        return ""


@app.route("/backup", methods=["POST"])
def backup():
    data = request.json

    if not isinstance(data, list) or len(data) < 3:
        return jsonify({"error": "Invalid request format"}), 400

    ai_label, history = data[0], data[1]

    # Redis 키 설정
    redis_key = f"{ai_label}:{ai_label}"
    r.set(redis_key, json.dumps(history, ensure_ascii=False))

    # 요약 처리 후 Redis에 저장
    summary = summarize_with_messages(history, get_prompt("summary"))  # messages를 history로 변경
    redis_summary_key = f"{ai_label}:{ai_label}:summary"
    r.set(redis_summary_key, summary)

    return jsonify({"status": "ok"})


@app.route("/<ai_label>")
def user_page(ai_label):
    # Redis 키 설정
    redis_key = f"{ai_label}:{ai_label}"
    redis_summary_key = f"{ai_label}:{ai_label}:summary"

    # Redis에서 읽기
    history_json = r.get(redis_key)
    history = []
    if history_json:
        try:
            loaded = json.loads(history_json)
            # ✅ 올바른 구조인지 확인
            if (
                    isinstance(loaded, list) and len(loaded) > 0
                    and isinstance(loaded[0], dict)
                    and "role" in loaded[0]
                    and "content" in loaded[0]
            ):
                history = loaded
            else:
                print("⚠️ Invalid history format detected, resetting to [].")
        except Exception as e:
            print(f"⚠️ Failed to parse history_json: {e}")

    summary = r.get(redis_summary_key) or ""

    # 시스템 프롬프트 업데이트
    system_prompt = get_prompt(ai_label)

    # 클라이언트에 내려줄 모든 정보
    config = {
        "ai_label": ai_label,
        "history": history,
        "summary": summary,
        "system_prompt": system_prompt
    }

    template_name = "test.html" if ai_label == "test" else "ui.html"
    return render_template(template_name, config=config)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))