document.addEventListener("DOMContentLoaded", () => {
    const input = document.getElementById("userInput");
    const sendBtn = document.getElementById("send");
    const sidView = document.getElementById("sidView");
    const chatArea = document.getElementById("chatArea");
    const debug = document.getElementById("debug");

    const config = window.MONDAY_CONFIG || {};
    const username = config.username || "unknown";
    const aiLabel = config.ai_label || "ai";
    let messages = config.history || [];
    let summary = config.summary || "";
    let systemPrompt = config.system_prompt || "You are a helpful assistant.";

    // 상단 라벨 표시
    sidView.textContent = `User: ${username} / AI Label: ${aiLabel}`;

    // 메시지 추가 함수
    function appendMessage(sender, text) {
        const newMsg = document.createElement("div");
        newMsg.innerHTML = `<strong>${sender}:</strong> ${text}`;
        chatArea.appendChild(newMsg);
        chatArea.scrollTop = chatArea.scrollHeight; // 스크롤을 가장 아래로 위치
    }

    // 시스템 메시지 추가 함수 (최신 메시지로 대체)
    function setSystemMessage(text) {
        const existingSystemMsg = document.querySelector(".system-message");
        if (existingSystemMsg) {
            // 이미 있는 시스템 메시지를 제거
            existingSystemMsg.remove();
        }
        const newSystemMsg = document.createElement("div");
        newSystemMsg.classList.add("system-message");
        newSystemMsg.innerHTML = `<strong>System:</strong> ${text}`;
        chatArea.appendChild(newSystemMsg);
    }

    // 초기화: 시스템 메시지 출력
    setSystemMessage(systemPrompt);

    // 메시지 전송 함수
    async function sendMessage() {
        const text = input.value.trim();
        if (!text) return;

        // 사용자 메시지 표시
        appendMessage(username, text);

        // 서버로 프록시 요청 등 ... (기존 요청 처리 로직 유지)
    }

    sendBtn.addEventListener("click", sendMessage);
    input.addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            sendMessage();
        }
    });
});