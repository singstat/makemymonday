let SID = null;

async function startSession(){
  const r = await fetch('/session/start', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({facts: []})
  });
  const j = await r.json();
  SID = j.session_id;
  document.getElementById('sidView').textContent = 'sid=' + SID + ' (facts '+j.facts_count+')';
}

async function endSession(){
  if(!SID) return;
  const body = new Blob([JSON.stringify({session_id: SID})], {type:'application/json'});
  navigator.sendBeacon('/session/end', body);
}

async function sendMessage(){
  const input = document.getElementById('userInput');
  const out = document.getElementById('out');
  const msg = (input.value || '').trim();
  out.textContent = '…전송 중';

  const url = '/monday?q=' + encodeURIComponent(msg || '상태 체크. 불필요한 말 없이 한 문장.')
             + (SID ? '&sid=' + SID : '');
  try {
    const res = await fetch(url);
    out.textContent = await res.text();
  } catch (e) {
    out.textContent = '[ERROR] ' + e;
  }
}

document.getElementById('send').addEventListener('click', sendMessage);
document.getElementById('userInput').addEventListener('keydown', e=>{
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
window.addEventListener('DOMContentLoaded', startSession);
window.addEventListener('beforeunload', endSession);
