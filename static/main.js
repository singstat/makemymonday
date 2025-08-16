// static/main.js

document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("userInput");
  const sendBtn = document.getElementById("send");
  const out = document.getElementById("out");
  const sidView = document.getElementById("sidView");

  const aiLabel = (window.MONDAY_CONFIG && window.MONDAY_CONFIG.ai_label) || "test_ai";
  const username = (window.MONDAY_CONFIG && window.MONDAY_CONFIG.username) || "unknown";

  // 사용자/AI 라벨 표시
  sidView.textContent = `User: ${username} / AI Label: ${aiLabel}`;

  // 기본 안내 문구
  out.textContent = "여기에 답변이 표시됩니다.";

  // 메시지 히스토리 배열
  const messages = [];

  function renderMessages() {
    // 최신 메시지가 위로 오도록 뒤집어서 join
    out.textContent = messages.slice().reverse().join("\n\n");
  }

  sendBtn.addEventListener("click", () => {
    const text = input.value.trim();
    if (!text) return;

    // 사용자 입력 추가 (앞쪽에 삽입)
    messages.push(`${username}: ${text}`);

    // AI 답변 추가 (앞쪽에 삽입)
    messages.push(`${aiLabel}: test answer`);

    // 갱신
    renderMessages();

    // 입력창 비우기
    input.value = "";

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
