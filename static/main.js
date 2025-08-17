document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("userInput");
  const sendBtn = document.getElementById("send");
  const sidView = document.getElementById("sidView");
  const messagesDiv = document.getElementById("messages");

  const aiLabel = (window.MONDAY_CONFIG && window.MONDAY_CONFIG.ai_label) || "test_ai";
  const username = (window.MONDAY_CONFIG && window.MONDAY_CONFIG.username) || "unknown";
  let messages = (window.MONDAY_CONFIG && window.MONDAY_CONFIG.history) || [];

  // 사용자 / AI 라벨 표시
  sidView.textContent = `User: ${username} / AI Label: ${aiLabel}`;

  // 메시지 추가 함수 (아래로 누적)
  function appendMessage(sender, text) {
    const newMsg = document.createElement("pre");
    newMsg.textContent = `${sender}: ${text}`;
    messagesDiv.appendChild(newMsg);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
  }

  // 기존 기록 로드
  messages.forEach(msg => {
    appendMessage(msg.role, msg.content);
  });

  // 입력 전송 이벤트
  async function sendMessage() {
    const text = input.value.trim();
    if (!text) return;

    // 사용자 메시지 표시
    appendMessage(username, text);

    // 메시지 히스토리에 추가
    messages.push({ role: "user", content: text });
    input.value = "";

    try {
      const resp = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: username,
          messages: messages,
          model: "gpt-4o-mini"
        })
      });

      const data = await resp.json();

      // ✅ 응답 구조를 무조건 출력해서 디버깅
      console.log("📥 /chat response:", data);

      const aiText = data.answer || data.error || "(empty)";
      appendMessage(aiLabel, aiText);

      // 히스토리에 AI 응답 추가
      messages.push({ role: "assistant", content: aiText });

    } catch (err) {
      console.error("❌ Fetch error:", err);
      appendMessage(aiLabel, "(fetch error)");
    }
  }

  sendBtn.addEventListener("click", sendMessage);
  input.addEventListener("keypress", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      sendMessage();
    }
  });

  // 페이지 닫힐 때 Redis 백업
  window.addEventListener("beforeunload", async () => {
    try {
      await fetch("/backup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: username,
          ai_label: aiLabel,
          history: messages
        })
      });
    } catch (err) {
      console.error("❌ Backup error:", err);
    }
  });
});
