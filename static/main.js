// static/main.js
(() => {
  const $input = document.getElementById('userInput');
  const $send  = document.getElementById('send');
  const $out   = document.getElementById('out');
  const $sid   = document.getElementById('sidView');

  const sid = (document.cookie.match(/(?:^|;\s*)sid=([^;]+)/) || [,''])[1];
  if ($sid) $sid.textContent = sid ? `sid: ${sid}` : '';

  // 서버 기록 + 이번 세션 신규 기록(업로드 대기)
  const messages = [];   // {text, ts}
  let queue = [];        // {text, ts} (서버 미전송분)

  const normTs = (t) => {
    const n = Number(t || Date.now());
    return n < 1e12 ? n * 1000 : n; // sec → ms 보정
  };

  const formatKST = (tsMs) => {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Seoul',
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hour12: false
    }).formatToParts(new Date(tsMs));
    const get = (type) => parts.find(p => p.type === type)?.value || '';
    return `${get('year')} ${get('month')} ${get('day')} ${get('hour')} ${get('minute')}`;
  };

  const render = () => {
    $out.textContent = messages.map(m => `${m.text} ${formatKST(m.ts)}`).join('\n');
  };

  async function loadHistory() {
    try {
      const res = await fetch(`/api/messages?sid=${encodeURIComponent(sid)}`, { credentials: 'same-origin' });
      const data = await res.json();
      if (data?.ok && Array.isArray(data.items)) {
        messages.splice(0, messages.length, ...data.items.map(it => ({
          text: String(it.text || '').trim(),
          ts: normTs(it.ts)
        })));
        render();
      }
    } catch { /* noop */ }
  }

  function handleSubmit(e) {
    e?.preventDefault?.();
    if (e?.type === 'keydown' && e.key === 'Enter' && (e.isComposing || e.keyCode === 229)) return;

    const text = ($input.value || '').trim();
    if (!text) return;

    const item = { text, ts: Date.now() }; // ts는 UTC 기준 ms, 표시만 KST로 포맷
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
    if (ok) queue = [];
    return ok;
  }

  $input.addEventListener('keydown', (e) => { if (e.key === 'Enter') handleSubmit(e); });
  $send.addEventListener('click', handleSubmit);

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flushQueueBeacon();
  });
  window.addEventListener('pagehide', flushQueueBeacon);
  window.addEventListener('beforeunload', flushQueueBeacon);

  loadHistory();
  $input.focus();
})();
