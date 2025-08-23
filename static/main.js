document.addEventListener("DOMContentLoaded", () => {
    const input = document.getElementById("userInput");
    const sendBtn = document.getElementById("send");
    const sidView = document.getElementById("sidView");
    const chatArea = document.getElementById("chatArea");
    const debug = document.getElementById("debug");

    // 서버에서 내려준 config
    const config = window.MONDAY_CONFIG || {};
    const aiLabel = config.ai_label || "ai";
    let messages = config.history || [];

    let systemPrompt = config.system_prompt || "Only answer what the user explicitly asks; do not add anything extra.";

    let summary = config.summary || ""; // 받아온 summary

    // Initialize the display of the summary
    if (summary) {
        summaryDisplay.innerText = `Summary: ${summary}`;
    } else {
        summaryDisplay.innerText = "No summary available."; // Summary가 없을 경우 메시지 표시
    }


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
        chatArea.scrollTop = chatArea.scrollHeight;
    }

    // 초기화: 과거 대화 불러오기
    messages.forEach(msg => {
        appendMessage(msg.role === "user" ? "User" : aiLabel, msg.content, msg.role);
    });

    // 메시지 전송 함수
    async function sendMessage() {
        const text = input.value.trim();
        if (!text) return;

        // 사용자 메시지 표시
        appendMessage("User", text, "user");
        messages.push({ role: "user", content: text });
        input.value = "";

        // 전체 메시지 배열
        const totalMessages = [
            { role: "system", content: systemPrompt },
            { role: "system", content: summary },
            ...messages
        ];

        try {
            const resp = await fetch("/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify([
                    aiLabel,         // ai_label
                    totalMessages,   // history (messages 포괄)
                    summary          // summary
                ])
            });

            const data = await resp.json();
            if (data.error) {
                appendMessage(aiLabel, "(error: " + data.error + ")", "assistant");
                appendDebugInfo("Error: " + data.error);
                return;
            }

            // clear_user_messages 신호 → 메시지 초기화
            if (data.clear_user_messages) {
                messages = [];
            }

            const aiText = data.answer || "(empty)";
            appendMessage(aiLabel, aiText, "assistant");
            messages.push({ role: "assistant", content: aiText });

        } catch (err) {
            console.error("❌ Fetch error:", err);
            appendMessage(aiLabel, "(fetch error)", "assistant");
            appendDebugInfo("Fetch error: " + err.message);
        }
    }

    // 브라우저 종료 시 메시지 백업
    window.addEventListener("beforeunload", () => {
        const data = JSON.stringify([aiLabel, messages, summary]);
        const blob = new Blob([data], { type: "application/json" });
        navigator.sendBeacon("/backup", blob);
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
