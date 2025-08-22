import datetime
import pytz

import datetime
import pytz

def get_current_kst():
    """현재 KST 날짜와 시간을 반환합니다."""
    kst = pytz.timezone("Asia/Seoul")  # KST 시간대 설정
    current_time = datetime.datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")  # KST 시간을 문자열로 변환
    return current_time

def get_prompt(ai_label):
    """AI 프롬프트를 반환하는 함수입니다."""
    current_time = get_current_kst()  # KST 현재 날짜와 시간 가져오기

    prompts = {
        "test": """Only answer what the user explicitly asks; do not add anything extra.
                    If the user requests code modifications, always provide the entire updated code
                    in a fully working state, not just partial changes.
                    Do not explain alternatives or unrelated technologies unless the user specifically asks.
                    Keep answers direct, minimal, and focused only on the question.""",
        "monday": f"You are a helpful assistant. Today's date in KST is {current_time}.",  # KST 날짜 포함
        "summary": "You are a helpful assistant. Please summarize the conversation.",
        "default": "You are a helpful assistant."
    }
    return prompts.get(ai_label, prompts["default"])