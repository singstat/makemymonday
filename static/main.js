let SID = null;

async function startSession(){
  const r = await fetch('/session/start', {method:'POST'});
  const j = await r.json();
  SID = j.session_id;
}
window.addEventListener('DOMContentLoaded', startSession);

// 페이지 닫힐 때 종료(브라우저 신뢰도 높게 sendBeacon 사용)
window.addEventListener('beforeunload', () => {
  if(!SID) return;
  const body = new Blob([JSON.stringify({session_id: SID})], {type:'application/json'});
  navigator.sendBeacon('/session/end', body);
});

// 네 기존 전송 함수에 sid만 붙여
async function sendMessage(){
  const input = document.getElementById('userInput');
  const out = document.getElementById('response');
  const msg = (input.value||'').trim();
  out.textContent = '…응답 대기중';

  const url = '/monday?q=' + encodeURIComponent(msg || '상태 체크. 불필요한 말 없이 한 문장.')
              + (SID ? '&sid='+SID : '');
  const res = await fetch(url);
  out.textContent = await res.text();
}

// (선택) 탭 살아있을 때 30초마다 ping
setInterval(()=>{
  if(!SID) return;
  fetch('/session/ping', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({session_id: SID})
  }).catch(()=>{});
}, 30000);
