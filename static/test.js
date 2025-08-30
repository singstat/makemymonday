// static/test.js

// ===== DOM refs & state =====
const message   = document.getElementById('message');
const summary   = document.getElementById('summary');
const input_txt = document.getElementById('input_txt');

let output_txt = "답변이 올거임";
let text_count = 0;                 // 모든 메시지 텍스트 길이 합
let hasSentOnExit = false;

const messagesData = [];            // { type:'sent'|'received', text:'...', ts:number }

// 페이지명: /test -> "test", /sdf -> "sdf"
const currentPageVar =
  window.currentPageVar ||
  (location.pathname.split("/").filter(Boolean).pop() || "unknown");

// 내부 규칙(줄바꿈 보존)
const summary_rule = `Update the existing summary with the new information from the conversation.
Keep previous requirements and code unless replaced.

Output only two sections:
1. Final requirements – updated bullet-point summary
2. Final code – the complete final working code (merged with updates).

Do not include intermediate reasoning, partial code, or rejected attempts.
Do not restate the conversation history.
Only provide the requirements summary and the final code.`;

// ===== AI trigger config =====
const AI_THRESHOLD = 300;  // text_count 임계값
let aiInFlight = false;    // 중복 호출 방지
let lastAITextCount = 0;   // 동일 길이에서 재호출 방지

// ===== utils =====
function appendBubble(text, type = "sent", record = true) {
  const b = document.createElement("div");
  b.className = `bubble ${type}`;
  b.textContent = text;
  message.appendChild(b);
  message.scrollTop = message.scrollHeight;

  // 누적 + 즉시 로그
  const addLen = (text || "").length;
  text_count += addLen;
  console.log("text_count =", text_count);

  if (record) {
    messagesData.push({ type, text, ts: Date.now() });
  }

  // AI 트리거 점검
  maybeTriggerAI();
}

window.setSummary = (text) => {
  summary.textContent = text || "";
};

window.setOutput = (text) => {
  output_txt = (text ?? "").toString();
};

// ===== AI trigger & call =====
function maybeTriggerAI() {
  if (text_count < AI_THRESHOLD) return;
  if (aiInFlight) return;
  if (lastAITextCount === text_count) return;

  aiInFlight = true;
  lastAITextCount = text_count;

  // 마지막 두 개 메시지를 제외한 대화만 요약에 사용
  const sliced = messagesData.slice(0, -2);   // 뒤에서 2개 제외
  const conversationDump = sliced
    .map((m) => `[${m.type}] ${m.text}`)
    .join("\n");

  const prompt = `${summary_rule}\n\n--- Conversation messages ---\n${conversationDump}`;

  summary.textContent = "요약 생성 중…";

  fetch("/api/ai", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  })
    .then((r) => r.json())
    .then((j) => {
      if (j && j.ok) {
        window.setSummary(j.output || "(빈 응답)");
      } else {
        window.setSummary(j && j.error ? `에러: ${j.error}` : "요약 실패");
      }
    })
    .catch((e) => {
      window.setSummary(`요약 실패(네트워크): ${e.message || e}`);
    })
    .finally(() => {
      aiInFlight = false;
    });
}

// ===== load saved messages on page load =====
async function loadMessages() {
  try {
    const res = await fetch(
      `/api/messages?page=${encodeURIComponent(currentPageVar)}`,
      { method: "GET" }
    );
    const data = await res.json();
    if (data && data.exists && Array.isArray(data.messages) && data.messages.length > 0) {
      // 저장된 스레드 렌더 + messagesData 기록 + text_count 증가(appendBubble 내부)
      data.messages.forEach((m) => {
        const t = m?.text ?? "";
        const ty = m?.type ?? "received";
        appendBubble(t, ty, true);
      });
      // 로딩 후에도 트리거 조건 충족 시 AI 호출
      maybeTriggerAI();
      return;
    }
  } catch (_) {
    // 무시하고 기본 프린트로 진행
  }

  // 없으면 기본 안내 출력
  window.setSummary("여기에 요약/설명 텍스트가 표시됩니다.");
  appendBubble("대화를 시작해보세요.", "received");
}

// ===== submit handler =====
document.getElementById("composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input_txt.value.trim();
  if (!text) return;

  appendBubble(text, "sent");
  input_txt.value = "";
  input_txt.focus();

  // 더미 답변도 출력
  appendBubble(output_txt, "received");
});

// ===== save on exit =====
function sendOnExit() {
  if (hasSentOnExit) return;
  hasSentOnExit = true;

  const payloadObj = { page: currentPageVar, messages: messagesData, text_count };
  const payload = JSON.stringify(payloadObj);

  try {
    const blob = new Blob([payload], { type: "application/json" });
    const ok = navigator.sendBeacon("/api/save_messages", blob);
    if (ok) return;
  } catch (_) {}

  try {
    fetch("/api/save_messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: payload,
      keepalive: true,
    }).catch(() => {});
  } catch (_) {}
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") sendOnExit();
});
window.addEventListener("pagehide", sendOnExit);
window.addEventListener("beforeunload", sendOnExit);

// ===== init =====
loadMessages();
