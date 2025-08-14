// static/main.js — URL 첫 세그먼트로 공간 구분
(() => {
  // ===== DOM =====
  const $input = document.getElementById('userInput');
  const $send  = document.getElementById('send');
  const $out   = document.getElementById('out');
  const $sidEl = document.getElementById('sidView'); // 공간 표시 용도


  // ===== Config =====
  const SUMMARY_KIND = 'summary';
  const BUDGET_TOKENS = 8000;
  const RESERVED_TOKENS = 1000;
  const SUMMARIZE_TRIGGER_TOKENS = 2000;
  const SUMMARY_MAX_CHARS = 1200;
  const SUMMARY_RECOMPRESS_CHARS = 1600;

  // ===== State =====
  if ($sidEl) $sidEl.textContent = `space: ${SPACE}`;
  const messages = []; // { role, text, ts, hidden?, kind?, persisted?, queued? }
  let queue = [];      // 업로드 대기(객체 참조)

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
  const visible = () => messages.filter(m => !m.hidden && m.kind !== SUMMARY_KIND);
  const latestSummary = () => { for (let i = messages.length - 1; i >= 0; i--) if (messages[i].kind === SUMMARY_KIND) return messages[i]; return null; };
  const enqueueOnce = (msg) => { if (!msg.queued) { queue.push(msg); msg.queued = true; } };

  // 턴 묶기(user → assistant)
  function splitTurns(list) {
    const turns = [];
    for (let i = 0; i < list.length; i++) {
      const m = list[i];
      if (m.role === 'user') {
        const t = [m];
        if (i + 1 < list.length && list[i + 1].role === 'assistant') { t.push(list[i + 1]); i++; }
        turns.push(t);
      } else if (m.role === 'assistant') {
        turns.push([m]); // 고아 assistant
      }
    }
    return turns;
  }


const SPACE = window.MONDAY_CONFIG?.space || 'default';
const AI_LABEL = window.MONDAY_CONFIG?.ai_label || 'assistant';

function render() {
  const vis = visible();
  const turns = splitTurns(vis);
  const older = turns.slice(0, Math.max(0, turns.length - 3));
  const last3 = turns.slice(-3);

  const toLines = (ts) => ts.flatMap(t =>
    t.map(m => `${m.role === 'user' ? '나' : AI_LABEL}: ${m.text || ''}`)
  );

  const topLines = toLines(older);
  const bottomLines = toLines(last3);
  const sep = (topLines.length && bottomLines.length) ? ['──────────── 최근 대화 ────────────'] : [];
  $out.textContent = [...topLines, ...sep, ...bottomLines].join('\n');

  const scroller = $out.parentElement || $out;
  scroller.scrollTop = scroller.scrollHeight;
}




  // 예산 강제: (summary 토큰 + visible 토큰) > 예산 → 오래된 visible부터 hidden
  function enforceBudget() {
    const budget = Math.max(1, BUDGET_TOKENS - RESERVED_TOKENS);
    const sumMsg = latestSummary();
    const sumSummary = sumMsg ? approxTokens(sumMsg.text || '') : 0;

    const vis = visible();
    let sumVisible = 0;
    for (let i = vis.length - 1; i >= 0; i--) sumVisible += approxTokens(vis[i].text);

    const allowedVisible = Math.max(0, budget - sumSummary);
    if (sumVisible <= allowedVisible) return;

    let toReduce = sumVisible - allowedVisible;
    for (const m of messages) {
      if (toReduce <= 0) break;
      if (m.hidden || m.kind === SUMMARY_KIND) continue;
      m.hidden = true;
      if (!m.persisted) enqueueOnce(m);
      toReduce -= approxTokens(m.text);
    }
  }

  // 요약 제외 hidden 토큰 합
  const hiddenNonSummaryTokens = () =>
    messages.filter(m => m.hidden && m.kind !== SUMMARY_KIND)
            .reduce((acc, m) => acc + approxTokens(m.text), 0);

  // 요약 존재 보장(빈 summary 1개)
  function ensureSummaryExists() {
    const has = messages.some(m => m.kind === SUMMARY_KIND);
    if (has) return;
    const summary = { role: 'system', text: '', ts: Date.now(), hidden: true, kind: SUMMARY_KIND, persisted: false, queued: false };
    messages.push(summary);
    enqueueOnce(summary);
  }

  // 안전 JSON
  async function safeJSON(res) {
    const ct = (res.headers.get('content-type') || '').toLowerCase();
    const body = await res.text();
    let data = null;
    if (ct.includes('application/json')) { try { data = JSON.parse(body); } catch {} }
    return { data, body };
  }

  // ===== 서버 I/O =====
  async function loadHistory() {
    try {
      const res = await fetch(`/api/${encodeURIComponent(SPACE)}/messages`, { credentials: 'same-origin' });
      const { data, body } = await safeJSON(res);
      if (!res.ok || !data?.ok) {
        console.error('History fetch failed', res.status, body.slice(0,200));
      } else {
        messages.splice(0, messages.length);
        for (const it of data.items) {
          messages.push({
            role: it.role === 'assistant' ? 'assistant' : (it.role === 'system' ? 'system' : 'user'),
            text: String(it.text || ''),
            ts: Number(it.ts || Date.now()),
            hidden: !!it.hidden,
            kind: it.kind || undefined,
            persisted: true,
            queued: false
          });
        }
      }
    } catch (e) {
      console.error('loadHistory failed', e);
    } finally {
      ensureSummaryExists();
      enforceBudget();
      render();
      maybeSummarize();
    }
  }

  async function askMonday(promptKST) {
    const history = messages.map(m => ({ role: m.role, text: m.text, ts: m.ts, hidden: !!m.hidden, kind: m.kind }));
    const res = await fetch(`/api/${encodeURIComponent(SPACE)}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ prompt: promptKST, history })
    });
    const { data, body } = await safeJSON(res);
    if (!res.ok || !data?.ok) throw new Error(data?.error || `${res.status} ${res.statusText}: ${body.slice(0,200)}`);
    return data.reply;
  }

  async function summarizeReq(items, prevSummary) {
    const res = await fetch(`/api/${encodeURIComponent(SPACE)}/summarize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ items, prev_summary: prevSummary, lang: 'ko', max_chars: SUMMARY_MAX_CHARS })
    });
    return safeJSON(res);
  }

  // 숨김(요약 제외) 전부 → 요약 생성 → summary 저장 → 원본 hidden 삭제
  async function maybeSummarize() {
    if (hiddenNonSummaryTokens() <= SUMMARIZE_TRIGGER_TOKENS) return;

    const items = messages
      .filter(m => m.hidden && m.kind !== SUMMARY_KIND && (m.text || '').trim())
      .map(m => ({ role: m.role === 'assistant' ? 'assistant' : 'user', text: m.text, ts: m.ts }));
    if (!items.length) return;

    let prev = (latestSummary()?.text || '').trim();
    try {
      let { data, body } = await summarizeReq(items, prev);
      if (!data?.ok) throw new Error(data?.error || `summarize: ${body.slice(0,200)}`);
      let sumText = String(data.summary || '').trim();
      if (!sumText) return;

      if (sumText.length > SUMMARY_RECOMPRESS_CHARS) {
        const r2 = await summarizeReq([], sumText);
        if (r2.data?.ok && (r2.data.summary || '').trim()) {
          sumText = String(r2.data.summary).trim();
        }
      }

      let sumMsg = latestSummary();
      if (!sumMsg) {
        sumMsg = { role: 'system', text: '', ts: Date.now(), hidden: true, kind: SUMMARY_KIND, persisted: false, queued: false };
        messages.push(sumMsg);
      }
      sumMsg.text = sumText;
      sumMsg.ts = Date.now();
      sumMsg.hidden = true;
      sumMsg.kind = SUMMARY_KIND;
      sumMsg.persisted = false;
      enqueueOnce(sumMsg);

      dropConvertedHiddenLocal();
      try {
        await fetch(`/api/${encodeURIComponent(SPACE)}/purge_hidden`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin'
        });
      } catch (e) {
        console.error('purge_hidden failed (ignored)', e);
      }

      enforceBudget();
      render();
      flushNow(); // 요약 즉시 저장
    } catch (e) {
      console.error('summarize failed', e);
    }
  }

  function dropConvertedHiddenLocal() {
    queue = queue.filter(m => !(m.hidden && m.kind !== SUMMARY_KIND));
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.hidden && m.kind !== SUMMARY_KIND) messages.splice(i, 1);
    }
  }

  // ===== 업로드 =====
  async function flushNow() {
    if (!queue.length) return;
    const payload = JSON.stringify({
      items: queue.map(m => ({ role: m.role, text: m.text, ts: m.ts, hidden: !!m.hidden, kind: m.kind }))
    });
    try {
      await fetch(`/api/${encodeURIComponent(SPACE)}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: payload
      });
      queue = [];
    } catch (e) { /* 실패 시 큐 유지 */ }
  }

  function flushQueueBeacon() {
    if (!queue.length) return true;
    const items = queue.map(m => ({ role: m.role, text: m.text, ts: m.ts, hidden: !!m.hidden, kind: m.kind }));
    const payload = JSON.stringify({ items });
    let ok = false;
    if (navigator.sendBeacon) {
      const blob = new Blob([payload], { type: 'application/json' });
      ok = navigator.sendBeacon(`/api/${encodeURIComponent(SPACE)}/messages`, blob);
    }
    if (!ok) {
      try {
        fetch(`/api/${encodeURIComponent(SPACE)}/messages`, {
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

  // ===== 핸들러 =====
  async function handleSubmit(e) {
    e?.preventDefault?.();
    if (e?.type === 'keydown' && e.key === 'Enter' && (e.isComposing || e.keyCode === 229)) return;

    const raw = ($input.value || '').trim();
    if (!raw) return;

    const ts = Date.now();
    const withKST = `${raw} ${formatKST(ts)}`;

    // user 메시지
    const u = { role: 'user', text: withKST, ts, hidden: false, persisted: false, queued: false };
    messages.push(u);
    enqueueOnce(u);

    $input.value = '';
    $input.focus();

    enforceBudget();
    render();
    flushNow();

    try {
      const reply = await askMonday(withKST);
      const a = { role: 'assistant', text: reply, ts: Date.now(), hidden: false, persisted: false, queued: false };
      messages.push(a);
      enqueueOnce(a);
      enforceBudget();
      render();
      flushNow();
    } catch (err) {
      const a = { role: 'assistant', text: `(에러) ${err.message || err}`, ts: Date.now(), hidden: false, persisted: false, queued: false };
      messages.push(a);
      enqueueOnce(a);
      enforceBudget();
      render();
      flushNow();
    }

    maybeSummarize();
  }

  // ===== 바인딩/시작 =====
  $input.addEventListener('keydown', (e) => { if (e.key === 'Enter') handleSubmit(e); });
  $send.addEventListener('click', handleSubmit);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') flushQueueBeacon(); });
  window.addEventListener('pagehide', flushQueueBeacon);
  window.addEventListener('beforeunload', flushQueueBeacon);
  setInterval(() => { flushNow(); }, 10_000);

  loadHistory();
  $input.focus();
})();
