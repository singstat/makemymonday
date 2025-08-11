console.log('main.js loaded');

let SID = sessionStorage.getItem('SID') || null;
const $btn = document.getElementById('send');
const $input = document.getElementById('userInput');
const $out = document.getElementById('out');
const $sid = document.getElementById('sidView');

async function startSession(){
  if (SID) { if ($sid) $sid.textContent = 'sid=' + SID; return; } // 이미 있으면 재사용
  try{
    const r = await fetch('/session/start', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({facts: []})
    });
    const j = await r.json();
    SID = j.session_id;
    sessionStorage.setItem('SID', SID);           // 🔵 저장
    if ($sid) $sid.textContent = 'sid=' + SID + ' (facts ' + j.facts_count + ')';
    console.log('session started', SID);
    $btn?.removeAttribute('disabled');
  }catch(e){
    console.error('session start failed', e);
    $out.textContent = '[ERROR] 세션 생성 실패';
  }
}

async function ensureSession(){
  if (!SID) { $btn?.setAttribute('disabled',''); await startSession(); }
  return !!SID;
}

async function sendMessage(){
  if (!(await ensureSession())) return;           // 🔵 보장
  const msg = ($input?.value || '').trim();
  if (!msg) return;
  $out.textContent = '…전송 중';
  try{
    const res = await fetch('/monday', {          // 🔵 항상 sid 포함
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ sid: SID, message: msg })
    });
    const text = await res.text();
    $out.textContent = text || '(빈 응답)';
  }catch(e){
    $out.textContent = '[ERROR] ' + e;
  }
  if ($input) $input.value = '';
}

// 초기화
window.addEventListener('DOMContentLoaded', async ()=>{
  $btn?.setAttribute('disabled','');             // 세션 전에 버튼 비활성화
  await startSession();
});
window.addEventListener('beforeunload', ()=>{
  if (!SID) return;
  const body = new Blob([JSON.stringify({session_id: SID})], {type:'application/json'});
  navigator.sendBeacon('/session/end', body);
});
$btn?.addEventListener('click', sendMessage);
$input?.addEventListener('keydown', e=>{
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});


// 페이지 닫힐 때 세션 종료
function endSession(){
  if(!SID) return;
  const body = new Blob([JSON.stringify({session_id: SID})], {type:'application/json'});
  navigator.sendBeacon('/session/end', body);
}

// 메시지 전송
let SENDING = false;

async function sendMessage(){
  if (SENDING) return;             // 중복 막기
  SENDING = true;

  const input = document.getElementById('userInput');
  const out   = document.getElementById('out');
  if (!input || !out) { console.error('DOM ids missing'); SENDING=false; return; }

  let msg = (input.value || '').trim();
  if (!msg) msg = '상태 체크. 불필요한 말 없이 한 문장.';

  // sid 보장: 저장된 거 쓰고, 없으면 startSession 시도
  if (!SID) SID = sessionStorage.getItem('SID');
  if (!SID && typeof startSession === 'function') { await startSession(); }
  const sid = SID || '';

  out.textContent = '…전송 중';
  try{
    const qs = new URLSearchParams({ q: msg, sid });
    const res = await fetch('/monday?' + qs.toString(), { cache: 'no-store' });
    const text = await res.text();
    out.textContent = text || '(빈 응답)';
  }catch(e){
    out.textContent = '[ERROR] ' + e;
  }finally{
    input.value = '';              // 전송 후 비우기
    SENDING = false;               // 락 해제
  }
}


// 이벤트 바인딩 (DOMContentLoaded 이후 보장)
window.addEventListener('DOMContentLoaded', () => {
  startSession();
  const btn = document.getElementById('send');
  const input = document.getElementById('userInput');
  if (btn)   btn.addEventListener('click', sendMessage);
  if (input) input.addEventListener('keydown', e=>{
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
});
window.addEventListener('beforeunload', endSession);
