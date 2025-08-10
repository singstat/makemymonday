const r = await fetch('/monday_stream?q='+encodeURIComponent(msg));
const reader = r.body.getReader(); let t='';
for await (const ch of (async function*(){for(;;){const {done,value}=await reader.read();if(done)break;yield value}})()){
  t += new TextDecoder().decode(ch); out.textContent = t;
}
