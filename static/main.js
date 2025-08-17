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
    let systemPrompt = config.system_prompt || "Only answer what the user explicitly asks; do not add anything extra.";

    // 상단 라벨
    sidView.textContent = `User: ${username} / AI Label: ${aiLabel}`;

    // 코드/텍스트 구분
    function isCodeLike(text) {
        return text.includes("<") && text.includes(">") || text.includes("```") || text.includes("\t");
    }

    // 메시지 추가
    function appendMessage(sender, text, role = "user") {
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
        chatArea.scrollTop = chatArea.scrollHeight;
    }

    // 시스템 메시지
    function setSystemMessage(text) {
        const existing = document.querySelector(".system-message");
        if (existing) existing.remove();
        const newMsg = document.createElement("div");
        newMsg.classList.add("system-message");
        newMsg.textContent = `System: ${text}`;
        chatArea.appendChild(newMsg);
    }

    // 디버그
    function appendDebugInfo(info) {
        const debugMsg = document.createElement("div");
        debugMsg.textContent = info;
        debugMsg.style.marginTop = "4px";
        debug.appendChild(debugMsg);
    }

    // 초기화
    setSystemMessage(systemPrompt);
    messages.forEach(msg => {
        appendMessage(msg.role === "user" ? username : aiLabel, msg.content, msg.role);
    });
    if (summary) appendDebugInfo("Summary: " + summary);

    // 메시지 전송
    async function sendMessage() {
        const text = input.value.trim();
        if (!text) return;

        appendMessage(username, text, "user");
        messages.push({ role: "user", content: text });
        input.value = "";

        try {
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

            appendDebugInfo("Response: " + JSON.stringify(data));

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

    sendBtn.addEventListener("click", sendMessage);
    input.addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            sendMessage();
        }
    });
});
