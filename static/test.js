// static/test.js
// 변수명 고정: message, summary, input_txt
const message   = document.getElementById('message');
const summary   = document.getElementById('summary');
const input_txt = document.getElementById('input_txt');

// 답변 변수 (초기 더미 값)
let output_txt = "답변이 올거임";

// 유틸: 말풍선 추가
function appendBubble(text, type = 'sent') {
  const b = document.createElement('div');
  b.className = `bubble ${type}`;
  b.textContent = text;
  message.appendChild(b);
  message.scrollTop = message.scrollHeight; // 최신으로 스크롤
}

// 제출 핸들러
document.getElementById('composer').addEventListener('submit', (e) => {
  e.preventDefault();
  const text = input_txt.value.trim();  // 사용자가 입력한 내용
  if (!text) return;

  // 1) 내가 쓴 텍스트 프린트
  appendBubble(text, 'sent');

  // 2) 입력값 저장(원하면 최근 입력을 전역에 남겨둠)
  window.last_input_txt = text;

  // 3) output_txt 프린트 (현재는 더미 응답)
  appendBubble(output_txt, 'received');

  // 4) 입력창 초기화 & 포커스
  input_txt.value = '';
  input_txt.focus();
});

// summary 갱신 함수
window.setSummary = (text) => {
  summary.textContent = text || '';
};

// 추후 실제 응답 바인딩을 위해 setter 제공 (선택)
window.setOutput = (text) => {
  output_txt = (text ?? '').toString();
};

// 초기 데모 데이터
window.setSummary('여기에 요약/설명 텍스트가 표시됩니다. 내용 길이에 따라 이 상자 내부에서만 스크롤됩니다.');
appendBubble('대화를 시작해보세요.', 'received');

function sendMessagesOnExit() {
  const page = (window.currentPageVar || location.pathname.split("/").filter(Boolean).pop() || "unknown");
  const payload = JSON.stringify({ page, messages: messagesData });
  const blob = new Blob([payload], { type: "application/json" });
  navigator.sendBeacon("/api/save_messages", blob);
}