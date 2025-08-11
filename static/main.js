// static/main.js
(() => {
  // ===== DOM =====
  const $input = document.getElementById('userInput');
  const $send  = document.getElementById('send');
  const $out   = document.getElementById('out');
  const $sidEl = document.getElementById('sidView');

  // ===== Config =====
  const SUMMARY_KIND = 'summary';
  const BUDGET_TOKENS = 8000;     // 전체 입력 예산(대략치)
  const RESERVED_TOKENS = 1000;   // 답변/시스템 여유
  const SUMMARIZE_TRIGGER_TOKENS = 2000; // 요약 제외 hidden 토큰이 넘으면 요약 생성

  // ===== State =====
  const sid = (document.cookie.match(/(?:^|;\s*)sid=([^;]+)/) || [,''])[1];
  if ($sidEl) $sidEl.textContent = sid ? `sid: ${sid}` : '';

  // message 객체:
  // { role:'user'|'assistant'|'system', text, ts, hidden?:bool, kind?:'summary', persisted?:bool, queued?:bool }
  const messages = [];
  let queue = []; // 업로드 대기(객체 참조 보관)

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
  const latestSummary = () => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].kind === SUMMARY_KIND) return messages[i];
    }
    return null;
  };

  const render = () => {
    const vis = visible();
    $out.textContent = vis.map(m => (m.role === 'user' ? `나: ${m.text}` : `monday: ${m.text}`)).join('\n');
  };

  function enqueueOnce(msg) {
    if (msg.queued) return;
    queue.push(msg);
    msg.queued = true;
  }

  // 예산 강제: (summary 토큰 + visible 토큰) > 예산 → 오래된 visible부터 hidden
  function enforceBudget() {
    const budget = Math.max(1, BUDGET_TOKENS - RESERVED_TOKENS);

    // 최신 summary만 고려(여러 개면 마지막 것을 현재 컨텍스트로 봄)
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
  function hiddenNonSummaryTokens() {
    return messages
      .filter(m => m.hidden && m.kind !== SUMMARY_KIND)
      .reduce((acc, m) => acc + approxTokens(m.text), 0);
  }

  // 요약 존재 보장(빈 텍스트, hidden)
  function ensureSummaryExists() {
    const has = messages.some(m => m.kind === SUMMARY_KIND);
    if (has) return;
    const ts = Date.now();
    const summary = { role: 'system', text: '', ts, hidden: true, kind: SUMMARY_KIND, persisted: false, queued: false };
    messages.push(summary);
    enqueueOnce(summary);
  }

  // 안전 JSON 파서(HTML 에러 페이지 대비)
  async function safeJSON(res) {
    const ct = (res.headers.get('content-type') || '').toLowerCase();
    const body = await res.text();
    let data = null;
    if (ct.includes('application/json')) { try { data = JSON.parse(body); } catch {} }
    return { data, body };
  }

  // 서버 히스토리 로딩
  async function loadHistory() {
    try {
      const res = await fetch(`/api/messages?sid=${encodeURIComponent(sid)}`, { credentials: 'same-origin' });
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
      // 로드 직후 숨김이 많다면 요약 시도
      maybeSummarize();
    }
  }

  // Chat 프록시 호출 (history 동봉)
  async function askMonday(promptKST) {
    const history = messages.map(m => ({
      role: m.role, text: m.text, ts: m.ts, hidden: !!m.hidden, kind: m.kind
    }));
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ prompt: promptKST, history })
    });
    const { data, body } = await safeJSON(res);
    if (!res.ok || !data?.ok) throw new Error(data?.error || `${res.status} ${res.statusText}: ${body.slice(0,200)}`);
    return data.reply;
  }

  // hidden(요약 제외) 전부로 요약 생성 → summary 생성/업로드 → 요약 제외 hidden 전부 삭제
  async function maybeSummarize() {
    const tokens = hiddenNonSummaryTokens();
    if (tokens <= SUMMARIZE_TRIGGER_TOKENS) return;

    // 내용 있는 summary가 이미 있으면 스킵(중복 방지)
    const existing = latestSummary();
    if (existing && (existing.text || '').trim().length > 0) return;

    // 1) 요약 입력: summary가 아닌 hidden 전부(역할 포함)
    const items = messages
      .filter(m => m.hidden && m.kind !== SUMMARY_KIND && (m.text || '').trim())
      .map(m => ({ role: m.role === 'assistant' ? 'assistant' : 'user', text: m.text, ts: m.ts }));
    if (!items.length) return;

    try {
      // 2) 사실만/맥락만/용량축소 지시
      const res = await fetch('/api/summarize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ items, lang: 'ko', max_chars: 1200 })
      });
      const { data, body } = await safeJSON(res);
      if (!res.ok || !data?.ok) throw new Error(data?.error || `summarize: ${res.status} ${body.slice(0,200)}`);

      const sumText = String(data.summary || '').trim();
      if (!sumText) return;

      // 3) summary(hidden) 만들기/갱신 + 큐에 태움
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

      // 4) 요약으로 대체된 hidden(요약 제외) 전부 삭제 — 로컬 & 서버 동기화
      dropConvertedHiddenLocal();
      try {
        await fetch('/api/purge_hidden', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ sid })
        });
      } catch (e) {
        console.error('purge_hidden failed (ignored)', e);
      }

      // 요약 크기에 따라 예산 재계산
      enforceBudget();
      render();

    } catch (e) {
      console.error('summarize failed', e);
    }
  }

  // 로컬에서 요약 제외 hidden 모두 제거 + 큐에서도 제거
  function dropConvertedHiddenLocal() {
    queue = queue.filter(m => !(m.hidden && m.kind !== SUMMARY_KIND));
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.hidden && m.kind !== SUMMARY_KIND) {
        messages.splice(i, 1);
      }
    }
  }

  // 업로드(이탈 시)
  function flushQueueBeacon() {
    if (!queue.length) return true;
    const items = queue.map(m => ({
      role: m.role, text: m.text, ts: m.ts, hidden: !!m.hidden, kind: m.kind
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
    if (ok) queue = [];
    return ok;
  }

  // ===== Handlers =====
  async function handleSubmit(e) {
    e?.preventDefault?.();
    // 한글 IME 조합 중 Enter 무시
    if (e?.type === 'keydown' && e.key === 'Enter' && (e.isComposing || e.keyCode === 229)) return;

    const raw = ($input.value || '').trim();
    if (!raw) return;

    const ts = Date.now();
    const withKST = `${raw} ${formatKST(ts)}`;

    // 사용자 발화 추가(visible)
    const u = { role: 'user', text: withKST, ts, hidden: false, persisted: false, queued: false };
    messages.push(u);
    enqueueOnce(u);

    // 입력창 비우고 렌더
    $input.value = '';
    $input.focus();
    enforceBudget();
    render();

    // Chat 호출 → 답변 추가 → 예산 재계산
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

    // 숨김이 임계치 넘으면 요약 생성 및 hidden 정리
    maybeSummarize();
  }

  // ===== Bindings =====
  $input.addEventListener('keydown', (e) => { if (e.key === 'Enter') handleSubmit(e); });
  $send.addEventListener('click', handleSubmit);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') flushQueueBeacon(); });
  window.addEventListener('pagehide', flushQueueBeacon);
  window.addEventListener('beforeunload', flushQueueBeacon);

  // ===== Init =====
  loadHistory();
  $input.focus();
})();
