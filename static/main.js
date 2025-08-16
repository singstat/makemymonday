// static/main.js

document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("userInput");
  const sendBtn = document.getElementById("send");
  const out = document.getElementById("out");
  const sidView = document.getElementById("sidView");

  // 서버에서 내려준 config 값 읽기
  const aiLabel = (window.MONDAY_CONFIG && window.MONDAY_CONFIG.ai_label) || "test_ai";
  const username = (window.MONDAY_CONFIG && window.MONDAY_CONFIG.username) || "unknown";

  // 항상 User + AI Label 같이 출력 (다른 코드가 덮어써도 이 값 유지됨)
  sidView.textContent = `User: ${username} / AI Label: ${aiLabel}`;

  // 기본 안내 메시지
  out.textContent = "여기에 답변이 표시됩니다.";

  // 전송 버튼 클릭 이벤트
  sendBtn.addEventListener("click", () => {
    const text = input.value.trim();
    if (!text) return;

    // 사용자 입력 반영
    out.textContent = "사용자 입력: " + text;

    // 입력창 비우기
    input.value = "";

    // 디버깅용 콘솔 출력
    console.log(`User(${username}) 입력:`, text);
  });

  // Enter 키로도 전송 가능
  input.addEventListener("keypress", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      sendBtn.click();
    }
  });
});
