// static/main.js
(() => {
  const $input = document.getElementById('userInput');
  const $send  = document.getElementById('send');
  const $out   = document.getElementById('out');

  // 누적 메시지 저장 (페이지 새로고침 시 유지하려면 localStorage 사용)
  const messages = [];

  function renderMessages() {
    $out.textContent = messages.join('\n');
  }

  function handleSubmit(e) {
    e?.preventDefault?.();
    const text = ($input.value || '').trim();
    if (!text) return;
    messages.push(text);
    renderMessages();
    $input.value = '';
    $input.focus();
  }

  // 엔터키
  $input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') handleSubmit(e);
  });

  // 버튼 클릭
  $send.addEventListener('click', handleSubmit);
})();
