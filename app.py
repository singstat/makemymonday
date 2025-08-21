from flask import Flask, render_template, request, jsonify
import os
import json
import redis
from openai import OpenAI

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
    """클라이언트가 맥락/메타데이터/질문을 전부 들고 와서 토큰 계산 후 OpenAI API 호출만 대신 해주는 단순 프록시."""
    data = request.json
    messages = data.get("messages", [])
    model = data.get("model", "gpt-4o-mini")  # 기본 모델
    system_prompt = data.get("system_prompt", "You are a helpful assistant.")

    # ✅ 토큰 계산
    token_count = count_tokens(messages)
    print(f"🔢 Token count = {token_count}")

    if token_count > 8192:
        # 요약 생성
        summary = summarize_with_messages(messages)

        # 메시지를 요약 버전으로 교체
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": summary}
        ]
    else:
        # 토큰 수가 제한 이하일 경우
        messages = [
            {"role": "system", "content": system_prompt},
            *messages
        ]

    try:
        # OpenAI API 호출
        resp = client.chat.completions.create(
            model=model,
            messages=messages
        )
        answer = resp.choices[0].message.content.strip()
        return jsonify({"answer": answer})
    except Exception as e:
        return jsonify({"error": str(e)}), 500



def summarize_with_messages(messages):
    """ 주어진 메시지 배열을 요약하는 함수 """
    if not messages:
        return ""  # 메시지가 없으면 빈 문자열 반환

    summary_prompt = """Update the existing summary with the new information from the conversation. 
Keep previous requirements and code unless replaced. 
Output only two sections:
1. Final requirements – updated bullet-point summary 
2. Final code – the complete final working code (merged with updates).


Do not include intermediate reasoning, partial code, or rejected attempts. 
Do not restate the conversation history. 
Only provide the requirements summary and the final code.\n"""
    for msg in messages:
        summary_prompt += f"{msg['role']}: {msg['content']}\n"  # 대화 조합

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": summary_prompt}]
        )
        summary = resp.choices[0].message.content.strip()
        return summary
    except Exception as e:
        print(f"Error summarizing messages: {str(e)}")
        return ""  # 에러 시 빈 문자열 반환


@app.route("/backup", methods=["POST"])
def backup():
    data = request.json
    print(f"📥 Received backup: {data}")  # 👈 확인용 로그

    if not isinstance(data, list) or len(data) < 3:
        return jsonify({"error": "Invalid request format"}), 400

    username, ai_label, history = data[0], data[1], data[2]

    # Redis 키 설정
    redis_key = f"{username}:{ai_label}"
    r.set(redis_key, json.dumps(history, ensure_ascii=False))

    # 요약 처리 후 Redis에 저장
    summary = summarize_with_messages(history)
    redis_summary_key = f"{username}:{ai_label}:summary"
    r.set(redis_summary_key, summary)

    return jsonify({"status": "ok"})

@app.route("/<username>")
def user_page(username):
    ai_label = "test" if username == "test" else "monday"

    # Redis 키 설정
    redis_key = f"{username}:{ai_label}"
    redis_summary_key = f"{username}:{ai_label}:summary"
    redis_system_key = f"{username}:{ai_label}:system"

    # Redis에서 읽기
    history_json = r.get(redis_key)
    history = json.loads(history_json) if history_json else []

    summary = r.get(redis_summary_key) or ""

    # 시스템 프롬프트 업데이트
    if username == "test":
        system_prompt = """Only answer what the user explicitly asks; do not add anything extra. 
                           If the user requests code modifications, always provide the entire updated code 
                           in a fully working state, not just partial changes. 
                           Do not explain alternatives or unrelated technologies unless the user specifically asks. 
                           Keep answers direct, minimal, and focused only on the question."""
    else:
        system_prompt = "You are a helpful assistant."  # 다른 사용자에 대한 기본 프롬프트

    # 클라이언트에 내려줄 모든 정보
    config = {
        "ai_label": ai_label,
        "username": username,
        "history": history,
        "summary": summary,
        "system_prompt": system_prompt
    }

    template_name = "test.html" if username == "test" else "ui.html"
    return render_template(template_name, config=config)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))