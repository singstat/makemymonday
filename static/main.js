fetch('/api/echo', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({ text })
})
