// static/test.js

// ===== DOM refs & state =====
const message   = document.getElementById('message');
const summary   = document.getElementById('summary');
const input_txt = document.getElementById('input_txt');
let output_txt  = "답변이 올거임";
const messagesData = []; // {type:'sent'|'received', text:'...', ts:number}
let hasSentOnExit = false;

// 새로운 변수: 모든 메시지 텍스트 길이 합산
let text_count = 0;

// 현재 페이지명: /test -> "test", /sdf -> "sdf"
const currentPageVar =
  (window.currentPageVar) ||
  (location.pathname.split('/').filter(Boolean).pop() || 'unknown');

// ===== utils =====
function appendBubble(text, type = 'sent', record = true) {
  const b = document.createElement('div');
  b.className = `bubble ${type}`;
  b.textContent = text;
  message.appendChild(b);
  message.scrollTop = message.scrollHeight;
  if (record) messagesData.push({ type, text, ts: Date.now() });
}

window.setSummary = (text) => {
  summary.textContent = text || '';
};

window.setOutput = (text) => {
  output_txt = (text ?? '').toString();
};

// ===== load saved messages on page load =====
async function loadMessages() {
  try {
    const res = await fetch(`/api/messages?page=${encodeURIComponent(currentPageVar)}`, { method: 'GET' });
    const data = await res.json();
    if (data && data.exists && Array.isArray(data.messages) && data.messages.length > 0) {
      // 저장된 스레드 복원
      data.messages.forEach(m => {
        const t  = (m && m.text) ? m.text : '';
        const ty = (m && m.type) ? m.type : 'received';
        appendBubble(t, ty, false);
      });
      // 이후 종료 시 저장을 위해 messagesData에도 추가
      data.messages.forEach(m => messagesData.push(m));
      return;
    }
  } catch (_) {
    // 실패 시 기본 프린트로 진행
  }
  // 없으면 기본 안내 출력
  window.setSummary('여기에 요약/설명 텍스트가 표시됩니다.');
  appendBubble('대화를 시작해보세요.', 'received');
}

// ===== submit handler =====
document.getElementById('composer').addEventListener('submit', (e) => {
  e.preventDefault();
  const text = input_txt.value.trim();
  if (!text) return;
  appendBubble(text, 'sent');
  input_txt.value = '';
  input_txt.focus();

  // 답변(현재는 더미 output_txt)도 출력
  appendBubble(output_txt, 'received');

  // 디버그: 콘솔에서 text_count 확인 가능
  console.log("text_count =", text_count);
});

// ===== save on exit =====
function sendOnExit() {
  if (hasSentOnExit) return;
  hasSentOnExit = true;

  const payloadObj = { page: currentPageVar, messages: messagesData };
  const payload = JSON.stringify(payloadObj);

  try {
    const blob = new Blob([payload], { type: 'application/json' });
    const ok = navigator.sendBeacon('/api/save_messages', blob);
    if (ok) return;
  } catch (_) {}

  try {
    fetch('/api/save_messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: payload,
      keepalive: true
    }).catch(()=>{});
  } catch (_) {}
}

// 다양한 종료 이벤트 훅
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') sendOnExit();
});
window.addEventListener('pagehide', sendOnExit);
window.addEventListener('beforeunload', sendOnExit);

// ===== init =====
loadMessages();
