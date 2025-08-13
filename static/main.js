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

  const render = () => {
    const vis = visible();
    $out.textContent = vis.map(m => (m.role === 'user' ? `나: ${m.text}` : `monday: ${m.text}`)).
