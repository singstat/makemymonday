// static/main.js
(() => {
  const $input = document.getElementById('userInput');
  const $send  = document.getElementById('send');
  const $out   = document.getElementById('out');
  const $sid   = document.getElementById('sidView');

  const sid = (document.cookie.match(/(?:^|;\s*)sid=([^;]+)/) || [,''])[1];
  if ($sid) $sid.textContent = sid ? `sid: ${sid}` : '';

  const messages = [];

  const render = () => { $out.textContent = messages.map(m => m.text).join('\n'); };

  async function loadHistory() {
    try {
      const res = await fetch(`/api/messages?sid=${encodeURIComponent(sid)}`, { credentials: 'same-origin' });
      const data = await res.json();
      if (data?.ok && Array.isArray(data.items)) {
        messages.splice(0, messages.length, ...data.items);
        render();
      }
    } catch (e) { /* noop */ }
  }

  async function saveToServer(text) {
    try {
      await fetch('/api/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ text })
      });
    } catch (e) { /* 실패해도 화면은 유지 */ }
  }

  function handleSubmit(e) {
    e?.preventDefault?.();
    if (e?.type === 'keydown' && e.key === 'Enter' && (e.isComposing || e.keyCode === 229)) return;

    const text = ($input.value || '').trim();
    if (!text) return;

    // 화면 즉시 반영
    messages.push({ text, ts: Date.now() });
    render();

    // 서버 저장 (실패해도 무시)
    saveToServer(text);

    // 입력창 비우기 (요구사항 1)
    $input.value = '';
    $input.focus();
  }

  $input.addEventListener('keydown', (e) => { if (e.key === 'Enter') handleSubmit(e); });
  $send.addEventListener('click', handleSubmit);

  loadHistory();
  $input.focus();
})();
