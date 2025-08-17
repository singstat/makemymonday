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

    // 메시지 추가 함수 (user/ai 구분)
     function appendMessage(sender, text, role="user") {
        const newMsg = document.createElement("div");
        newMsg.classList.add("msg", role);
        // \n → <br> 변환해서 줄바꿈 반영
        newMsg.innerHTML = `<strong>${sender}:</strong><br>${text.replace(/\n/g, "<br>")}`;
        chatArea.appendChild(newMsg);
        chatArea.scrollTop = chatArea.scrollHeight; // 항상 맨 아래로
    }

    // 디버그 정보 추가 함수
    function appendDebugInfo(info) {
        debug.innerHTML = '';
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
                appendMessage(aiLabel, "(error: " + data.error + ")", "ai");
                appendDebugInfo("Error: " + data.error);
                return;
            }

            const aiText = data.answer || "(empty)";
            appendMessage(aiLabel, aiText, "ai");
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
            appendMessage(aiLabel, "(fetch error)", "ai");
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
