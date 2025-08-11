// static/main.js
(() => {
  const $input = document.getElementById('userInput');
  const $send  = document.getElementById('send');
  const $out   = document.getElementById('out');
  const $sid   = document.getElementById('sidView');

  const sid = (document.cookie.match(/(?:^|;\s*)sid=([^;]+)/) || [,''])[1];
  if ($sid) $sid.textContent = sid ? `sid: ${sid}` : '';

  const messages = []; // [{role: 'user'|'assistant', text, ts}]
  let queue = [];      // 업로드 대기

  const pad2 = (n) => String(n).padStart(2, '0');
  const formatKST = (tsMs) => {
    const d = new Date(tsMs);
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Seoul',
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hour12: false
    }).formatToParts(d);
    const get = (t) => parts.find(p => p.type === t)?.value || '';
    return `${get('year')} ${get('month')} ${get('day')} ${get('hour')} ${get('minute')}`;
  };

  const render = () => {
    $out.textContent = messages.map(m =>
      (m.role === 'user' ? `나: ${m.text}` : `monday: ${m.text}`)
    ).join('\n');
  };

  // 서버 히스토리 불러오기
  async function loadHistory() {
    try {
      const res = await fetch(`/api/messages?sid=${encodeURIComponent(sid)}`, { credentials: 'same-origin' });
      const data = await res.json();
      if (data?.ok && Array.isArray(data.items)) {
        messages.splice(0, messages.length, ...data.items.map(it => ({
          role: it.role === 'assistant' ? 'assistant' : 'user',
          text: String(it.text || ''),
          ts: Number(it.ts || Date.now())
        })));
        render();
      }
    } catch {}
  }

  // Chat 호출
  async function askMonday(promptKST) {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ prompt: promptKST })
    });
    const data = await res.json();
    if (!res.ok || !data?.ok) throw new Error(data?.error || 'chat failed');
    return data.reply;
  }

  async function handleSubmit(e) {
    e?.preventDefault?.();
    if (e?.type === 'keydown' && e.key === 'Enter' && (e.isComposing || e.keyCode === 229)) return;

    const raw = ($input.value || '').trim();
    if (!raw) return;

    const ts = Date.now();
    const withKST = `${raw} ${formatKST(ts)}`;

    // 로컬 누적 (user)
    const u = { role: 'user', text: withKST, ts };
    messages.push(u);
    queue.push(u);
    render();

    // 입력창 비움
    $input.value = '';
    $input.focus();

    // 서버로 프록시 호출 → 답변 로컬 누적 (assistant)
    try {
      const reply = await askMonday(withKST);
      const a = { role: 'assistant', text: reply, ts: Date.now() };
      messages.push(a);
      queue.push(a);
      render();
    } catch (err) {
      const a = { role: 'assistant', text: `(에러) ${err.message || err}`, ts: Date.now() };
      messages.push(a);
      queue.push(a);
      render();
    }
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

  // 바인딩
  $input.addEventListener('keydown', (e) => { if (e.key === 'Enter') handleSubmit(e); });
  $send.addEventListener('click', handleSubmit);

  // 페이지 이탈 시 업로드
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flushQueueBeacon();
  });
  window.addEventListener('pagehide', flushQueueBeacon);
  window.addEventListener('beforeunload', flushQueueBeacon);

  loadHistory();
  $input.focus();
})();
