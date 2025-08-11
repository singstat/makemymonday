// static/main.js
(() => {
  const $input = document.getElementById('userInput');
  const $send  = document.getElementById('send');
  const $out   = document.getElementById('out');
  const $sidEl = document.getElementById('sidView');

  // ===== Config (토큰 예산) =====
  const BUDGET_TOKENS = 8000;    // 입력 예산
  const RESERVED_TOKENS = 1000;  // 답변/시스템 여유

  // ===== State =====
  const sid = (document.cookie.match(/(?:^|;\s*)sid=([^;]+)/) || [,''])[1];
  if ($sidEl) $sidEl.textContent = sid ? `sid: ${sid}` : '';

  // 메시지:
  // - visible: 화면에 보이는 항목
  // - hidden: 토큰 예산 초과로 잘려 '보이지 않게' 저장되는 항목
  // 공통 필드: { role: 'user'|'assistant', text, ts, hidden?:boolean, persisted?:boolean, queued?:boolean }
  const messages = [];

  // 업로드 대기 큐 (이번 세션에서 새로 생긴 항목만 넣음)
  let queue = [];

  // ===== Utils =====
  const formatKST = (tsMs) => {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Seoul',
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hour12: false
    }).formatToParts(new Date(tsMs));
    const get = (t) => parts.find(p => p.type === t)?.value || '';
    return `${get('year')} ${get('month')} ${get('day')} ${get('hour')} ${get('minute')}`;
  };

  const approxTokens = (s) => Math.max(1, Math.ceil(String(s).length / 2));

  const visible = () => messages.filter(m => !m.hidden);
  const render = () => {
    $out.textContent = visible()
      .map(m => m.role === 'user' ? `나: ${m.text}` : `monday: ${m.text}`)
      .join('\n');
  };

  // 예산 강제: 오래된 visible부터 hidden으로 이동
  function enforceBudget() {
    const budget = Math.max(1, BUDGET_TOKENS - RESERVED_TOKENS);
    let sum = 0;
    const vis = visible();
    // 최신부터 역순으로 토큰 누적
    for (let i = vis.length - 1; i >= 0; i--) {
      sum += approxTokens(vis[i].text);
    }
    if (sum <= budget) return; // 여유 있음

    // 초과량만큼 앞에서부터 hidden 처리
    let toReduce = sum - budget;
    for (const m of messages) {
      if (m.hidden) continue; // 이미 hidden
      const t = approxTokens(m.text);
      if (toReduce <= 0) break;
      // 앞쪽 visible부터 숨김
      m.hidden = true;

      // 이미 서버에 저장된 것(persisted)은 큐에 넣지 않음
      if (!m.persisted && !m.queued) {
        queue.push({ role: m.role, text: m.text, ts: m.ts, hidden: true });
        m.queued = true;
      }
      toReduce -= t;
    }
  }

  // ===== Server I/O =====
  async function loadHistory() {
    try {
      const res = await fetch(`/api/messages?sid=${encodeURIComponent(sid)}`, { credentials: 'same-origin' });
      const data = await res.json();
      if (data?.ok && Array.isArray(data.items)) {
        messages.splice(0, messages.length);
        for (const it of data.items) {
          messages.push({
            role: it.role === 'assistant' ? 'assistant' : 'user',
            text: String(it.text || ''),
            ts: Number(it.ts || Date.now()),
            hidden: !!it.hidden,
            persisted: true,   // 서버에서 온 건 이미 저장됨
            queued: false
          });
        }
        // 로딩 직후에도 예산을 맞춰 visible/hidden을 정리(과거 visible도 숨길 수 있음)
        enforceBudget();
        render();
      }
    } catch (e) {
      console.error('loadHistory failed', e);
    }
  }

  async function askMonday(promptKST) {
    const history = messages.map(m => ({
      role: m.role,
      text: m.text,
      ts: m.ts,
      hidden: !!m.hidden,
    }));
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ prompt: promptKST, history })
    });
    const data = await res.json();
    if (!res.ok || !data?.ok) throw new Error(data?.error || 'chat failed');
    return data.reply;
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

  // ===== Handlers =====
  async function handleSubmit(e) {
    e?.preventDefault?.();
    if (e?.type === 'keydown' && e.key === 'Enter' && (e.isComposing || e.keyCode === 229)) return;

    const raw = ($input.value || '').trim();
    if (!raw) return;

    const ts = Date.now();
    const withKST = `${raw} ${formatKST(ts)}`;

    // 1) 사용자 발화 추가 (초기엔 visible)
    const u = { role: 'user', text: withKST, ts, hidden: false, persisted: false, queued: false };
    messages.push(u);
    queue.push({ role: u.role, text: u.text, ts: u.ts, hidden: false });
    u.queued = true;

    // 입력창 비우고 먼저 렌더
    $input.value = '';
    $input.focus();

    // 2) 예산 강제 (앞부분을 hidden으로 이동하며, 새로 숨긴 항목은 큐에 hidden:true로 추가)
    enforceBudget();
    render();

    // 3) 챗 호출 → 답변 누적(visible로 시도) → 다시 예산 강제
    try {
      const reply = await askMonday(withKST);
      const a = { role: 'assistant', text: reply, ts: Date.now(), hidden: false, persisted: false, queued: false };
      messages.push(a);
      queue.push({ role: a.role, text: a.text, ts: a.ts, hidden: false });
      a.queued = true;

      enforceBudget();
      render();
    } catch (err) {
      const a = { role: 'assistant', text: `(에러) ${err.message || err}`, ts: Date.now(), hidden: false, persisted: false, queued: false };
      messages.push(a);
      queue.push({ role: a.role, text: a.text, ts: a.ts, hidden: false });
      a.queued = true;

      enforceBudget();
      render();
    }
  }

  // ===== Bindings =====
  $input.addEventListener('keydown', (e) => { if (e.key === 'Enter') handleSubmit(e); });
  $send.addEventListener('click', handleSubmit);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') flushQueueBeacon(); });
  window.addEventListener('pagehide', flushQueueBeacon);
  window.addEventListener('beforeunload', flushQueueBeacon);

  // Init
  loadHistory();
  $input.focus();
})();
