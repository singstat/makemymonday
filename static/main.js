document.addEventListener("DOMContentLoaded", () => {
    const input = document.getElementById("userInput");
    const sendBtn = document.getElementById("send");
    const sidView = document.getElementById("sidView");
    const chatArea = document.getElementById("chatArea");
    const debug = document.getElementById("debug");

    // 서버에서 내려준 config
    const config = window.MONDAY_CONFIG || {};
    const username = config.username || "unknown";
    const aiLabel = config.ai_label || "ai";
    let messages = config.history || [];
    let summary = config.summary || "";
    let systemPrompt = config.system_prompt || "Only answer what the user explicitly asks; do not add anything extra.";

    // 상단 라벨 표시
    sidView.textContent = `User: ${username} / AI Label: ${aiLabel} / Token: 100`;

    // 코드/텍스트 구분 함수
    function isCodeLike(text) {
        return text.includes("```") || text.includes("\t");
    }

    // 메시지 추가 함수
    function appendMessage(sender, text, role = "assistant") {
        let newMsg;
        if (isCodeLike(text)) {
            newMsg = document.createElement("pre");
            newMsg.classList.add("msg", role, "code");
            newMsg.textContent = `${sender}:\n${text}`;
        } else {
            newMsg = document.createElement("div");
            newMsg.classList.add("msg", role);
            newMsg.innerText = `${sender}: ${text}`;
        }
        chatArea.appendChild(newMsg);
        chatArea.scrollTop = chatArea.scrollHeight; // Auto scroll to the bottom
    }

    // 시스템 메시지 설정 함수
    function setSystemMessage(text) {
        const existing = document.querySelector(".system-message");
        if (existing) existing.remove(); // 기존 시스템 메시지 제거
        const newMsg = document.createElement("div");
        newMsg.classList.add("system-message");
        newMsg.textContent = `System: ${text}`;
        chatArea.appendChild(newMsg); // 새로운 시스템 메시지 추가
    }

    // 디버그 정보 추가 함수
    function appendDebugInfo(info) {
        debug.innerHTML = ''; // 기존의 모든 디버깅 메시지를 제거
        const debugMsg = document.createElement("div");
        debugMsg.textContent = info;
        debugMsg.style.marginTop = "4px"; // 여백 추가
        debug.appendChild(debugMsg); // 새로운 디버깅 정보 추가
    }

    // 초기화: 과거 대화, 요약, 시스템 메시지 출력
    messages.forEach(msg => {
        appendMessage(msg.role === "user" ? username : aiLabel, msg.content, msg.role);
    });
    if (summary) appendDebugInfo("Summary: " + summary);

    // 메시지 전송 함수
    async function sendMessage() {
        const text = input.value.trim();
        if (!text) return;

        // 사용자 메시지 화면에 표시
        appendMessage(username, text, "user");
        messages.push({ role: "user", content: text });
        input.value = ""; // 입력 필드 비우기

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
                appendDebugInfo("Error: " + data.error);
                return;
            }

            const aiText = data.answer || "(empty)";
            appendMessage(aiLabel, aiText, "assistant");
            messages.push({ role: "assistant", content: aiText });

            // 디버깅 로그
            appendDebugInfo("Response: " + JSON.stringify(data));

        } catch (err) {
            console.error("❌ Fetch error:", err);
            appendMessage(aiLabel, "(fetch error)", "assistant");
            appendDebugInfo("Fetch error: " + err.message);
        }
    }

    // 브라우저 종료 시 메시지 백업
    window.addEventListener("beforeunload", async () => {
        await fetch("/backup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, ai_label: aiLabel, history: messages })
        });
    });

    // 이벤트 바인딩
    sendBtn.addEventListener("click", sendMessage);
    input.addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            sendMessage();
        }
    });
});