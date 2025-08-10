async function sendMessage() {
  const input = document.getElementById('userInput');
  const out = document.getElementById('response');
  const msg = (input.value || '').trim();
  out.textContent = '…응답 대기중';

  try {
    const res = await fetch('/monday?q=' + encodeURIComponent(msg || '상태 체크. 불필요한 말 없이 한 문장.'));
    const text = await res.text();
    out.textContent = text || '(빈 응답)';
  } catch (e) {
    out.textContent = '[ERROR] ' + e;
  }
}
