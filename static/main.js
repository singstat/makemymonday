// static/main.js
(() => {
  const $input = document.getElementById('userInput');
  const $send  = document.getElementById('send');
  const $out   = document.getElementById('out');
  const $sid   = document.getElementById('sidView');

  const sid = (document.cookie.match(/(?:^|;\s*)sid=([^;]+)/) || [,''])[1];
  if ($sid) $sid.textContent = sid ? `sid: ${sid}` : '';

  // 서버 기록 + 이번 세션 신규 기록(업로드 대기)
  const messages = [];       // 화면 표시용(서버 히스토리 + 신규)
  let queue = [];            // 서버 미전송분만 저장

  const render = () => { $out.textContent = messages.map(m => m.text).join('\n'); };

  async function loadHistory() {
    try {
      const res = await fetch(`/api/messages?sid=${encodeURIComponent(sid)}`, { credentials: 'same-origin' });
      const data = await res.json();
      if (data?.ok && Array.isArray(data.items)) {
        messages.splice(0, messages.length, ...data.items);
        render();
      }
    } catch { /* noop */ }
  }

  function handleSubmit(e) {
    e?.preventDefault?.();
    // IME 조합 중 Enter 방지
    if (e?.type === 'keydown' && e.key === 'Enter' && (e.isComposing || e.keyCode === 229)) return;

    const text = ($input.value || '').trim();
    if (!text) return;

    const item = { text, ts: Date.now() };
    messages.push(item); // 화면 누적
    queue.push(item);    // 서버 업로드 대기
    render();

    $input.value = '';
    $input.focus();
  }

  function flushQueueBeacon() {
    if (!queue.length) return true;
    const payload = JSON.stringify({ sid, items: queue });
    let ok = false;

    if (navigator.sendBeacon) {
      const blob = new Blob([payload], { type: 'application/json' });
      ok = navigator.sendBeacon('/api/messages', blob);
    }
    if (!ok) {
      try {
        fetch('/api/messages', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: payload,
          keepalive: true,
          credentials: 'same-origin'
        });
        ok = true;
      } catch { ok = false; }
    }
    if (ok) queue = []; // 성공 가정 후 비움
    return ok;
  }

  // 이벤트
  $input.addEventListener('keydown', (e) => { if (e.key === 'Enter') handleSubmit(e); });
  $send.addEventListener('click', handleSubmit);

  // 페이지 이탈 시 업로드
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flushQueueBeacon();
  });
  window.addEventListener('pagehide', flushQueueBeacon);
  window.addEventListener('beforeunload', flushQueueBeacon);

  // 초기 로드
  loadHistory();
  $input.focus();
})();
