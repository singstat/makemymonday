// static/main.js
(() => {
  // ============= DOM =============
  const $input = document.getElementById('userInput');
  const $send  = document.getElementById('send');
  const $out   = document.getElementById('out');
  const $sidEl = document.getElementById('sidView');

  // =========== Config ============
  const SUMMARY_KIND = 'summary';
  const BUDGET_TOKENS = 8000;        // 전체 입력 예산(대략치)
  const RESERVED_TOKENS = 1000;      // 답변/시스템 여유
  const SUMMARIZE_TRIGGER_TOKENS = 2000; // 요약 제외 hidden 토큰 임계치
  const SUMMARY_MAX_CHARS = 1200;    // 요약 목표 길이
  const SUMMARY_RECOMPRESS_CHARS = 1600; // 넘어가면 요약만 재압축 시도

  // ============ State ============
  const sid = (document.cookie.match(/(?:^|;\s*)sid=([^;]+)/) || [,''])[1];
  if ($sidEl) $sidEl.textContent = sid ? `sid: ${sid}` : '';

  // 메시지 객체 형태:
  // { role:'user'|'assistant'|'system', text, ts, hidden?:bool, kind?:'summary', persisted?:bool, queued?:bool }
  const messages = [];
  let queue = []; // 업로드 대기(객체 참조로 보관 → hidden 전환 시 상태 반영)

  // ============ Utils ============
  const formatKST = (tsMs) => {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hour12: false
    }).formatToParts(new Date(tsMs));
    const get = (t) => parts.find(p => p.type === t)?.value || '';
    return `${get('year')} ${get('month')} ${get('day')} ${get('hour')} ${get('minute')}`;
  };
  const approxTokens = (s) => Math.max(1, Math.ceil(String(s).length / 2));
  const visible = () => messages.filter(m => !m.hidden && m.kind !== SUMMARY_KIND);
  const latestSummary = () => {
    for (let i = messages.length - 1; i >= 0; i--) if (messages[i].kind === SUMMARY_KIND) return messages[i];
    return null;
  };
  const enqueueOnce = (msg) => { if (!msg.queued) { queue.push(msg); msg.queued = true; } };

  // --- 추가: 턴( user → assistant )으로 묶기 ---
function splitTurns(list) {
  const turns = [];
  for (let i = 0; i < list.length; i++) {
    const m = list[i];
    if (m.role === 'user') {
      const turn = [m];
      if (i + 1 < list.length && list[i + 1].role === 'assistant') {
        turn.push(list[i + 1]);
        i++; // 어시스턴트까지 한 턴으로 소모
      }
      turns.push(turn);
    } else if (m.role === 'assistant') {
      // 고아 assistant도 개별 턴으로 취급
      turns.push([m]);
    }
  }
  return turns;
}

// --- 교체: render() (최근 3턴 위, 구분선, 나머지 아래) ---
const render = () => {
  // 화면에 보일 항목만: hidden/summary 제외
  const vis = messages.filter(m => !m.hidden && m.kind !== 'summary');

  const turns = splitTurns(vis);
  const last3 = turns.slice(-3);
  const older = turns.slice(0, Math.max(0, turns.length - 3));

  const toLines = (ts) =>
    ts.flatMap(t =>
      t.map(m => (m.role === 'user' ? `나: ${m.text}` : `monday: ${m.text}`))
    );

  const topLines = toLines(last3);      // 최근 3턴 (시간순 유지)
  const bottomLines = toLines(older);   // 그 이전 턴들

  const sep = (topLines.length && bottomLines.length)
    ? ['──────────── 이전 대화 ────────────']
    : [];

  $out.textContent = [...topLines, ...sep, ...bottomLines].join('\n');
};


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

  // 요약 존재 보장(빈 텍스트 hidden summary가 없으면 생성)
  function ensureSummaryExists() {
    const has = messages.some(m => m.kind === SUMMARY_KIND);
    if (has) return;
    const ts = Date.now();
    const summary = { role: 'system', text: '', ts, hidden: true, kind: SUMMARY_KIND, persisted: false, queued: false };
    messages.push(summary);
    enqueueOnce(summary);
  }

  // 안전 JSON 파서(HTML 에러 페이지 방지)
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
      // 로드 직후에도 숨김이 많으면 요약 시도
      maybeSummarize();
    }
  }

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

  // 요약: summary 아닌 hidden 전부 → 서버 요약 → summary 저장 → 숨겨진 원본 제거
  async function maybeSummarize() {
    const tokens = hiddenNonSummaryTokens();
    if (tokens <= SUMMARIZE_TRIGGER_TOKENS) return;

    // 1) 입력 준비
    const items = messages
      .filter(m => m.hidden && m.kind !== SUMMARY_KIND && (m.text || '').trim())
      .map(m => ({ role: m.role === 'assistant' ? 'assistant' : 'user', text: m.text, ts: m.ts }));
    if (!items.length) return;

    const prev = (latestSummary()?.text || '').trim();

    try {
      // 2) 롤링 요약(이전+신규 → 더 작게)
      const res = await fetch('/api/summarize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ items, prev_summary: prev, lang: 'ko', max_chars: SUMMARY_MAX_CHARS })
      });
      const { data, body } = await safeJSON(res);
      if (!res.ok || !data?.ok) throw new Error(data?.error || `summarize: ${res.status} ${body.slice(0,200)}`);

      let sumText = String(data.summary || '').trim();
      if (!sumText) return;

      // 2.5) 요약이 너무 길면 요약 자체 재압축
      if (sumText.length > SUMMARY_RECOMPRESS_CHARS) {
        const res2 = await fetch('/api/summarize', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ items: [], prev_summary: sumText, lang: 'ko', max_chars: SUMMARY_MAX_CHARS })
        });
        const { data: d2 } = await safeJSON(res2);
        if (res2.ok && d2?.ok && (d2.summary || '').trim()) {
          sumText = String(d2.summary).trim();
        }
      }

      // 3) summary(hidden) 만들기/갱신 + 업로드 큐 등록
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

      // 4) 원본 hidden(요약 제외) 로컬/서버 모두 삭제
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

      enforceBudget();
      render();
    } catch (e) {
      console.error('summarize failed', e);
    }
  }

  function dropConvertedHiddenLocal() {
    // 큐에서 제거
    queue = queue.filter(m => !(m.hidden && m.kind !== SUMMARY_KIND));
    // 메시지 배열에서 제거(역순)
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.hidden && m.kind !== SUMMARY_KIND) {
        messages.splice(i, 1);
      }
    }
  }

  // ===== 업로드(페이지 이탈 시) =====
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

  // ============ Handlers ============
  async function handleSubmit(e) {
    e?.preventDefault?.();
    // 한글 IME 조합 중 Enter 무시
    if (e?.type === 'keydown' && e.key === 'Enter' && (e.isComposing || e.keyCode === 229)) return;

    const raw = ($input.value || '').trim();
    if (!raw) return;

    const ts = Date.now();
    const withKST = `${raw} ${formatKST(ts)}`;

    // 1) 사용자 발화(visible) → 로컬/큐
    const u = { role: 'user', text: withKST, ts, hidden: false, persisted: false, queued: false };
    messages.push(u);
    enqueueOnce(u);

    // 입력창 비움 + 우선 렌더
    $input.value = '';
    $input.focus();
    enforceBudget();
    render();

    // 2) Chat 호출 → 어시스턴트 응답(visible) → 로컬/큐
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

    // 3) 숨김이 많아지면 요약 생성 → 원본 hidden 정리
    maybeSummarize();
  }

  // ============ Bindings ============
  $input.addEventListener('keydown', (e) => { if (e.key === 'Enter') handleSubmit(e); });
  $send.addEventListener('click', handleSubmit);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') flushQueueBeacon(); });
  window.addEventListener('pagehide', flushQueueBeacon);
  window.addEventListener('beforeunload', flushQueueBeacon);

  // ============ Init ============
  loadHistory();
  $input.focus();
})();
