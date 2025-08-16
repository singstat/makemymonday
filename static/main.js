document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("userInput");
  const sendBtn = document.getElementById("send");
  const out = document.getElementById("out");
  const sidView = document.getElementById("sidView");

  const aiLabel = (window.MONDAY_CONFIG && window.MONDAY_CONFIG.ai_label) || "test_ai";
  const username = (window.MONDAY_CONFIG && window.MONDAY_CONFIG.username) || "unknown";
  const history = (window.MONDAY_CONFIG && window.MONDAY_CONFIG.history) || [];

  sidView.textContent = `User: ${username} / AI Label: ${aiLabel}`;

  function render(messages) {
    out.textContent = messages.slice().reverse().join("\n\n");
  }

  // 페이지 로딩 시 이전 기록 출력
  render(history);

  sendBtn.addEventListener("click", async () => {
    const text = input.value.trim();
    if (!text) return;

    // 서버에 사용자 입력 전달
    const resp = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, ai_label: aiLabel, text })
    });
    const data = await resp.json();

    // 서버 응답(messages 배열)을 history에 누적
    history.push(...data.messages);

    render(history);
    input.value = "";
  });

  input.addEventListener("keypress", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      sendBtn.click();
    }
  });

  // 세션 종료 시 Redis 백업
  window.addEventListener("beforeunload", () => {
    const payload = JSON.stringify({ username, ai_label: aiLabel, history });
    const blob = new Blob([payload], { type: "application/json" });
    navigator.sendBeacon("/backup", blob);
  });
});

