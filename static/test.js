// static/test.js
// ===== 상태 =====
const message   = document.getElementById('message');
const summary   = document.getElementById('summary');
const input_txt = document.getElementById('input_txt');
let output_txt  = "답변이 올거임";
const messagesData = []; // {type:'sent'|'received', text:'...', ts:number}
let hasSentOnExit = false;

// 현재 페이지명: /test -> "test", /sdf -> "sdf"
const currentPageVar =
  (window.currentPageVar) ||
  (location.pathname.split("/").filter(Boolean).pop() || "unknown");

// ===== UI 유틸 =====
function appendBubble(text, type = 'sent') {
  const b = document.createElement('div');
  b.className = `bubble ${type}`;
  b.textContent = text;
  message.appendChild(b);
  message.scrollTop = message.scrollHeight;
  messagesData.push({ type, text, ts: Date.now() });
}

// ===== 입력 핸들러 =====
document.getElementById('composer').addEventListener('submit', (e) => {
  e.preventDefault();
  const text = input_txt.value.trim();
  if (!text) return;
  appendBubble(text, 'sent');
  input_txt.value = '';
  input_txt.focus();

  // 답변(현재 더미)도 같이 출력
  appendBubble(output_txt, 'received');
});

// ===== summary setter =====
window.setSummary = (text) => {
  summary.textContent = text || '';
};

// ===== 종료 전송 =====
function sendOnExit() {
  if (hasSentOnExit) return;
  hasSentOnExit = true;

  const payloadObj = {
    page: currentPageVar,
    messages: messagesData
  };
  const payload = JSON.stringify(payloadObj);

  // 1) sendBeacon 시도
  try {
    const blob = new Blob([payload], { type: "application/json" });
    const ok = navigator.sendBeacon("/api/save_messages", blob);
    if (ok) return; // 큐에 성공적으로 넣음(보장X지만 최선)
  } catch (_) {}

  // 2) 실패 시 keepalive fetch 백업
  try {
    fetch("/api/save_messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: payload,
      keepalive: true
    }).catch(() => {});
  } catch (_) {}
}

// 다양한 종료/백그라운드 이벤트 훅
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") sendOnExit();
});
window.addEventListener("pagehide", () => {
  // bfcache 진입 포함
  sendOnExit();
});
window.addEventListener("beforeunload", () => {
  // 마지막 백업 훅(호환성 목적)
  sendOnExit();
});

// ===== 디버깅을 위한 핑 버튼(원하면 주석 처리) =====
window.ping = () => {
  fetch("/api/ping", { method: "POST", keepalive: true })
    .then(() => console.log("[ping] sent"))
    .catch(() => console.log("[ping] failed"));
};

// ===== 초기 데모 =====
window.setSummary('현재 페이지: ' + currentPageVar);
appendBubble('대화를 시작해보세요.', 'received');
