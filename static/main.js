// static/main.js
(() => {
  const $input = document.getElementById('userInput');
  const $send  = document.getElementById('send');
  const $out   = document.getElementById('out');

  const messages = [];

  function renderMessages() {
    $out.textContent = messages.join('\n');
  }

  function handleSubmit() {
    const text = ($input.value || '').trim();
    if (!text) return;
    messages.push(text);
    renderMessages();
    $input.value = '';
    $input.focus();
  }

  // IME(한글 등) 조합 중 Enter 방지
  $input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      // 조합 중(한글 입력)에는 무시
      if (e.isComposing || e.keyCode === 229) return;
      e.preventDefault();
      handleSubmit();
    }
  });

  $send.addEventListener('click', (e) => {
    e.preventDefault();
    handleSubmit();
  });
})();
