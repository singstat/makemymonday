document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("userInput");
  const sendBtn = document.getElementById("send");
  const out = document.getElementById("out");
  const sidView = document.getElementById("sidView");

  const config = window.MONDAY_CONFIG || {};
  const aiLabel = config.ai_label || "test_ai";
  const username = config.username || "unknown";

  // 상태 표시
  sidView.textContent = `User: ${username} / AI Label: ${aiLabel}`;

  // 대화 내역 (클라가 전부 관리)
  let history = [];

  // system prompt 분기
  let systemPrompt = "";
  if (username === "test") {
    systemPrompt =
      "Provide one action item at a time, do not suggest unnecessary implementations, and implement only the functionality I specify exactly.";
  } else {
    systemPrompt = ""; // monday 기본값
  }

  // 메시지 출력 함수 (위로 누적)
  function appendMessage(sender, text) {
    const newMsg = document.createElement("pre");
    newMsg.textContent = `${sender}: ${text}`;
    out.parentNode.insertBefore(newMsg, out); // 위에 누적
  }

  // 초기 히스토리 복원
  if (config.history && Array.isArray(config.history)) {
    config.history.forEach((msg) => {
      appendMessage(msg.role, msg.content);
      history.push(msg);
    });
  }

  // AI 응답 받기
  async function sendToAI(userText) {
    // 대화 메시지 구성
    let messages = [];

    // system prompt 맨 앞에 항상 유지
    messages.push({ role: "system", content: systemPrompt });

    // 지금까지의 히스토리 + 새 유저 메시지
    history.forEach((msg) => messages.push(msg));
    messages.push({ role: "user", content: userText });

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
      if (data.answer) {
        appendMessage(aiLabel, data.answer);
        history.push({ role: "user", content: userText });
        history.push({ role: "assistant", content: data.answer });
      } else {
        appendMessage(aiLabel, "⚠️ 오류 발생: " + (data.error || "unknown"));
      }
    } catch (err) {
      appendMessage(aiLabel, "⚠️ 요청 실패: " + err.message);
    }
  }

  // 전송 버튼
  sendBtn.addEventListener("click", () => {
    const text = input.value.trim();
    if (!text) return;

    appendMessage(username, text);
    input.value = "";
    sendToAI(text);
  });

  // 엔터키
  input.addEventListener("keypress", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      sendBtn.click();
    }
  });

  // 브라우저 종료 시 Redis 백업
  window.addEventListener("beforeunload", () => {
    fetch("/backup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: username,
        ai_label: aiLabel,
        payload: { history: history }
      }),
      keepalive: true // 브라우저가 닫히는 순간에도 요청 시도
    });
  });
});

// JSON 디버그 프린트 함수
function printDebug(data) {
  if (username === "test") {
    const debugEl = document.getElementById("debug");
    debugEl.textContent = JSON.stringify(data, null, 2);
  }
}

// sendToAI 내부에서 서버에 보낼 JSON을 프린트
async function sendToAI(userText) {
  let messages = [];

  // system prompt 항상 첫 요소
  messages.push({ role: "system", content: systemPrompt });
  history.forEach((msg) => messages.push(msg));
  messages.push({ role: "user", content: userText });

  const payload = {
    username: username,
    messages: messages,
    model: "gpt-4o-mini"
  };

  // ✅ test 모드일 때만 디버깅 정보 출력
  printDebug(payload);

  try {
    const resp = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    ...
