// static/main.js
(() => {
  // ====== DOM ======
  const $input = document.getElementById('userInput');
  const $send  = document.getElementById('send');
  const $out   = document.getElementById('out');
  const $sidEl = document.getElementById('sidView');

  // ====== Config ======
  const SUMMARY_KIND = 'summary';
  const BUDGET_TOKENS = 8000;    // 입력 토큰 예산(대략치)
  const RESERVED_TOKENS = 1000;  // 답변/시스템 여유

  // ====== State ======
  const sid = (document.cookie.match(/(?:^|;\s*)sid=([^;]+)/) || [,''])[1];
  if ($sidEl) $sidEl.textContent = sid ? `sid: ${sid}` : '';

  // 메시지 오브젝트 형식:
  // { role:'user'|'assistant'|'system', text:string, ts:number, hidden?:boolean, kind?:'summary', persisted?:boolean, queued?:boolean }
  const messages = [];
  // 업로드 큐: 메시지 오브젝트 "참조"를 넣는다(복제 X) → hidden 변경 시 자동 반영
  let queue = [];

  // ====== Utils ======
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

  function enqueueOnce(msg) {
    if (msg.queued) return;
    queue.push(msg);
    msg.queued = true;
  }

  // 예산 강제: 최신 기준으로 총 토큰이 예산을 넘으면 "가장 오래된 visible"부터 hidden 처리
  function enforceBudget() {
    const budget = Math.max(1, BUDGET_TOKENS - RESERVED_TOKENS);
    const vis = visible();
    let sum = 0;
    for (let i = vis.length - 1; i >= 0; i--) {
      sum += approxTokens(vis[i].text);
    }
    if (sum <= budget) return;

    let toReduce = sum - budget;
    for (const m of messages) {
      if (m.hidden) continue;          // 이미 숨김
      if (m.kind === SUMMARY_KIND) continue; // 요약은 어차피 hidden이지만 혹시 대비
      if (toReduce <= 0) break;

      // 오래된 visible부터 숨김
      m.hidden = true;

      // 아직 서버에 저장되지 않은 메시지라면 큐에 (참조로) 추가
      if (!m.persisted) enqueueOnce(m);

      toReduce -= approxTokens(m.text);
    }
  }

  // ====== Server I/O ======
  async function loadHistory() {
    try {
      const res = await fetch(`/api/messages?sid=${encodeURIComponent(sid)}`, { credentials: 'same-origin' });
      const data = await res.json();
      if (data?.ok && Array.isArray(data.items)) {
        messages.splice(0, messages.length);
        for (const it of data.items) {
          messages.push({
            role: it.role === 'assistant' ? 'assistant' : (it.role === 'system' ? 'system' : 'user'),
            text: String(it.text || ''),
            ts: Number(it.ts || Date.now()),
            hidden: !!it.hidden,
            kind: it.kind || undefined,
            persisted: true,   // 서버에서 온 항목은 이미 저장된 것으로 처리
            queued: false
          });
        }
        enforceBudget();
        ensureSummaryExists(); // 없으면 빈 요약 생성
        render();
      } else {
        ensureSummaryExists();
        render();
      }
    } catch (e) {
      console.error('loadHistory failed', e);
      ensureSummaryExists();
      render();
    }
  }

  // /api/chat 호출 (현재 세션의 전체 history 동봉: hidden/summary 포함)
  async function askMonday(promptKST) {
    const history = messages.map(m => ({
      role: m.role,
      text: m.text,
      ts: m.ts,
      hidden: !!m.hidden,
      kind: m.kind
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

    // 큐에 들어있는 "메시지 오브젝트"를 JSON 페이로드로 변환
    const items = queue.map(m => ({
      role: m.role,
      text: m.text,
      ts: m.ts,
      hidden: !!m.hidden,
      kind: m.kind
    }));
    const payload = JSON.stringify({ sid, items });
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
    if (ok) queue = []; // 성공 가정 후 큐 비움(네트워크 실패시 유실 가능-규칙 유지)
    return ok;
  }

  // ====== Summary ======
  function ensureSummaryExists() {
    const has = messages.some(m => m.kind === SUMMARY_KIND);
    if (has) return;
    const ts = Date.now();
    const summary = {
      role: 'system',
      text: '',          // 빈 요약
      ts,
      hidden: true,      // 항상 숨김
      kind: SUMMARY_KIND,
      persisted: false,
      queued: false
    };
    messages.push(summary);
    enqueueOnce(summary); // 기존 규칙대로 업로드 큐에 넣음
  }

  // ====== Handlers ======
  async function handleSubmit(e) {
    e?.preventDefault?.();
    // 한글 IME 조합 중 Enter 무시
    if (e?.type === 'keydown' && e.key === 'Enter' && (e.isComposing || e.keyCode === 229)) return;

    const raw = ($input.value || '').trim();
    if (!raw) return;

    const ts = Date.now();
    const withKST = `${raw} ${formatKST(ts)}`;

    // 사용자 발화 추가 (초기 visible)
    const u = { role: 'user', text: withKST, ts, hidden: false, persisted: false, queued: false };
    messages.push(u);
    enqueueOnce(u);

    // 입력창 비우고 먼저 렌더
    $input.value = '';
    $input.focus();

    // 예산 강제 & 렌더
    enforceBudget();
    render();

    // 챗 호출 → 어시스턴트 응답 추가 (초기 visible) → 다시 예산 강제
    try {
      const reply = await askMonday(withKST);
      const a = { role: 'assistant', text: reply, ts: Date.now(), hidden: false, persisted: false, queued: false };
      messages.push(a);
      enqueueOnce(a);

      enforceBudget();
      render();
    } catch (err) {
      const a = { role: 'assistant', text: `(에러) ${err.message || err}`, ts: Date.now(), hidden: false, persisted: false, queued: false };
      messages.push(a);
      enqueueOnce(a);

      enforceBudget();
      render();
    }
  }

  // ====== Bindings ======
  $input.addEventListener('keydown', (e) => { if (e.key === 'Enter') handleSubmit(e); });
  $send.addEventListener('click', handleSubmit);

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flushQueueBeacon();
  });
  window.addEventListener('pagehide', flushQueueBeacon);
  window.addEventListener('beforeunload', flushQueueBeacon);

  // ====== Init ======
  loadHistory();
  $input.focus();
})();
