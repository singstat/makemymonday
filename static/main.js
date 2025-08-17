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
    let systemPrompt = config.system_prompt || "You are a helpful assistant.";

    // 상단 라벨 표시
    sidView.textContent = `User: ${username} / AI Label: ${aiLabel}`;

    // 코드/일반 메시지 구분 함수
    function isCodeLike(text) {
        // HTML 태그가 있거나, 백틱 코드블록이 있거나, 탭이 포함된 경우 → 코드로 간주
        return text.includes("<") && text.includes(">") || text.includes("```") || text.includes("\t");
    }

    // 메시지 추가 함수
    function appendMessage(sender, text, role = "user") {
        let newMsg;

        if (isCodeLike(text)) {
            // 코드 메시지는 <pre> + textContent → 브라우저가 실행하지 않고 원문 출력
            newMsg = document.createElement("pre");
            newMsg.classList.add("msg", role, "code");
            newMsg.textContent = `${sender}:\n${text}`;
        } else {
            // 일반 메시지는 <div> + innerText
            newMsg = document.createElement("div");
            newMsg.classList.add("msg", role);
            newMsg.innerText = `${sender}: ${text}`;
        }

        chatArea.appendChild(newMsg);
        chatArea.scrollTop = chatArea.scrollHeight;
    }

    // 디버그 정보 추가 함수
    function appendDebugInfo(info) {
        const debugMsg = document.createElement("div");
        debugMsg.textContent = info;
        debugMsg.style.marginTop = "4px";
        debug.appendChild(debugMsg);
    }

    // --- 초기화: 과거 대화/요약/시스템 메시지 출력 ---
    messages.forEach(msg => {
        appendMessage(
            msg.role === "user" ? username : aiLabel,
            msg.content,
            msg.role
        );
    });
    if (summary) appendDebugInfo("Summary: " + summary);
    if (systemPrompt) appendDebugInfo("System: " + systemPrompt);

    // 메시지 전송 함수
    async function sendMessage() {
        const text = input.value.trim();
        if (!text) return;

        // 사용자 메시지 화면에 표시
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
                appendDebugInfo("Error: " + data.error);
                return;
            }

            const aiText = data.answer || "(empty)";
            appendMessage(aiLabel, aiText, "assistant");
            messages.push({ role: "assistant", content: aiText });

            // 디버깅 로그
            appendDebugInfo("Response: " + JSON.stringify(data));

            // 백업 요청 (클라가 들고 있는 messages 전송)
            await fetch("/backup", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, ai_label: aiLabel, history: messages })
            });

        } catch (err) {
            console.error("❌ Fetch error:", err);
            appendMessage(aiLabel, "(fetch error)", "assistant");
            appendDebugInfo("Fetch error: " + err.message);
        }
    }

    // 이벤트 바인딩
    sendBtn.addEventListener("click", sendMessage);
    input.addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            sendMessage();
        }
    });
});
