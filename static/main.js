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

    // 코드/텍스트 구분
    function isCodeLike(text) {
        return text.includes("<") && text.includes(">") || text.includes("```") || text.includes("\t");
    }

    // 메시지 추가 함수
    function appendMessage(sender, text, role = "user") {
        let newMsg;

        if (isCodeLike(text)) {
            // 코드 메시지
            newMsg = document.createElement("pre");
            newMsg.classList.add("msg", role, "code");
            newMsg.textContent = `${sender}:\n${text}`;
        } else {
            // 일반 메시지
            newMsg = document.createElement("div");
            newMsg.classList.add("msg", role);
            newMsg.innerText = `${sender}: ${text}`;
        }

        chatArea.appendChild(newMsg);
        chatArea.scrollTop = chatArea.scrollHeight;
    }

    // 시스템 메시지 출력 (항상 최신으로 대체)
    function setSystemMessage(text) {
        const existing = document.querySelector(".system-message");
        if (existing) existing.remove();

        const newMsg = document.createElement("div");
        newMsg.classList.add("system-message");
        newMsg.textContent = `System: ${text}`;
        chatArea.appendChild(newMsg);
    }

    // 디버그 로그 추가
    function appendDebugInfo(info) {
        const debugMsg = document.createElement("div");
        debugMsg.textContent = info;
        debugMsg.style.marginTop = "4px";
        debug.appendChild(debugMsg);
    }

    // 초기화: 과거 대화 복원 + 시스템 메시지 + 요약 표시
    setSystemMessage(systemPrompt);
    messages.forEach(msg => {
        appendMessage(msg.role === "user" ? username : aiLabel, msg.content, msg.role);
    });
    if (summary) appendDebugInfo("Summary: " + summary);

    // 메시지 전송 함수
    async function sendMessage() {
        const text = input.value.trim();
        if (!text) return;

        // 사용자 메시지 표시
        appendMessage(username, text, "user");
        messages.push({ role: "user", content: text });
        input.value = "";

        try {
            // 서버로 프록시 요청
            const resp = await fetch("/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    username,
                    messages: [
                        { role: "system", content: systemPrompt },
                        ...messages
                    ]
                })
            });

            const data = await resp.json();
            if (data.error) {
                appendMessage(aiLabel, "(error: " + data.error + ")", "assistant");
                appendDebugInfo("
