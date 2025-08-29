// static/test.js
// 변수명 고정: message, summary, input_txt
const message   = document.getElementById('message');
const summary   = document.getElementById('summary');
const input_txt = document.getElementById('input_txt');

// 답변 변수: 아직은 더미 스트링을 저장만 함
let output_txt = "답변이 올거임";

// 유틸: 말풍선 추가
function appendBubble(text, type = 'sent') {
  const b = document.createElement('div');
  b.className = `bubble ${type}`;
  b.textContent = text;
  message.appendChild(b);
  message.scrollTop = message.scrollHeight; // 최신으로 스크롤
}

// 제출 핸들러: 내가 쓴 텍스트를 화면에 프린트
document.getElementById('composer').addEventListener('submit', (e) => {
  e.preventDefault();
  const text = input_txt.value.trim();  // 입력 내용은 input_txt 변수의 value에 저장됨
  if (!text) return;
  appendBubble(text, 'sent');
  input_txt.value = '';
  input_txt.focus();

  // (참고) 현재는 output_txt를 출력하지 않고 보관만 함
  // console.log('output_txt:', output_txt);
});

// summary 갱신 함수
window.setSummary = (text) => {
  summary.textContent = text || '';
};

// 초기 데모 데이터
window.setSummary('여기에 요약/설명 텍스트가 표시됩니다. 내용 길이에 따라 이 상자 내부에서만 스크롤됩니다.');
appendBubble('대화를 시작해보세요.', 'received');
