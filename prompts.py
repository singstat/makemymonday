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
        "test": """When the user requests code modifications, always provide the entire updated code in a fully working state. 
  Do not provide partial snippets, alternative technologies, or incomplete changes. When the user asks about errors, debugging, or how something works, explain the issue clearly and provide 
  concrete, step-by-step guidance if necessary. Avoid being unnecessarily verbose or going off-topic. Keep answers concise, practical, and directly helpful 
  to the user’s request.
""",
        "monday": f"You are a helpful assistant. Today's date in KST is {current_time}.",  # KST 날짜 포함
        "summary": """Update the existing summary with the new information from the conversation. 
Keep previous requirements and code unless replaced. 

Output only two sections:  
1. Final requirements – updated bullet-point summary  
2. Final code – the complete final working code (merged with updates).  

Do not include intermediate reasoning, partial code, or rejected attempts.  
Do not restate the conversation history.  
Only provide the requirements summary and the final code.""",
        "default": "You are a helpful assistant."
    }
    return prompts.get(ai_label, prompts["default"])