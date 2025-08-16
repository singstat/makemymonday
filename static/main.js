// static/main.js

document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("userInput");
  const sendBtn = document.getElementById("send");
  const out = document.getElementById("out");
  const sidView = document.getElementById("sidView");

  // 서버에서 내려온 값 확인
  console.log("MONDAY_CONFIG:", window.MONDAY_CONFIG);

  // 기본 출력
  out.textContent = "여기에 답변이 표시됩니다.";

  // sidView에 ai_label 표시 (없으면 기본 test_ai)
const aiLabel = (window.MONDAY_CONFIG && window.MONDAY_CONFIG.ai_label) || "test_ai";
const username = (window.MONDAY_CONFIG && window.MONDAY_CONFIG.username) || "unknown";
sidView.textContent = `User: ${username} / AI Label: ${aiLabel}`;

  // 전송 버튼 클릭 이벤트
  sendBtn.addEventListener("click", () => {
    const text = input.value.trim();
    if (!text) return;

    // 화면에 입력값 출력
    out.textContent = "사용자 입력: " + text;

    // 입력창 초기화
    input.value = "";
  });

  // Enter 키로도 전송 가능
  input.addEventListener("keypress", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      sendBtn.click();
    }
  });
});
