document.addEventListener("DOMContentLoaded", () => {
    const input = document.getElementById("userInput");
    const sendBtn = document.getElementById("send");
    const sidView = document.getElementById("sidView");
    const chatArea = document.getElementById("chatArea"); // 메시지 영역
    const debug = document.getElementById("debug"); // 디버그 정보 영역

    const aiLabel = (window.MONDAY_CONFIG && window.MONDAY_CONFIG.ai_label) || "test_ai";
    const username = (window.MONDAY_CONFIG && window.MONDAY_CONFIG.username) || "unknown";
    let messages = (window.MONDAY_CONFIG && window.MONDAY_CONFIG.history) || [];

    // 사용자 / AI 라벨 표시
    sidView.textContent = `User: ${username} / AI Label: ${aiLabel}`;

    // 메시지 추가 함수
    function appendMessage(sender, text) {
        const newMsg = document.createElement("pre");
        newMsg.textContent = `${sender}: ${text}`;
        chatArea.appendChild(newMsg); // chatArea에 메시지 추가
        chatArea.scrollTop = chatArea.scrollHeight; // 스크롤을 가장 아래로 위치
    }

    // 디버그 정보 추가 함수
    function appendDebugInfo(info) {
        const debugMsg = document.createElement("div");
        debugMsg.textContent = info;
        debugMsg.style.marginTop = "4px"; // 여백 추가
        debug.appendChild(debugMsg); // debug 영역에 디버깅 정보 추가
    }

    // 입력 전송 이벤트
    async function sendMessage() {
        const text = input.value.trim();
        if (!text) return;

        // 사용자 메시지 표시
        appendMessage(username, text);

        // 메시지 히스토리에 추가
        messages.push({ role: "user", content: text });

        input.value = ""; // 입력 필드 비우기

        // 응답 요청 및 처리
        try {
            const resp = await fetch("/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username: username, messages: messages })
            });

            const data = await resp.json();
            const aiText = data.answer || "(empty)";
            appendMessage(aiLabel, aiText); // AI의 응답 표시
            messages.push({ role: "assistant", content: aiText }); // AI 응답을 히스토리에 추가

            // 디버깅 정보 추가
            appendDebugInfo("AI response received successfully.");
        } catch (err) {
            console.error("❌ Fetch error:", err);
            appendMessage(aiLabel, "(fetch error)"); // 에러 메시지 표시
            appendDebugInfo("Error fetching AI response."); // 디버깅 정보 추가
        }
    }

    sendBtn.addEventListener("click", sendMessage);
    input.addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            sendMessage();
        }
    });
});