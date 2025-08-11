// static/main.js
(() => {
  const $input = document.getElementById('userInput');
  const $send  = document.getElementById('send');

  function clearInput() {
    if (!$input) return;
    $input.value = '';
    $input.focus();
  }

  function handleSubmit(e) {
    e?.preventDefault?.();
    clearInput();
  }

  if ($input) {
    $input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') handleSubmit(e);
    });
  }

  if ($send) {
    $send.addEventListener('click', handleSubmit);
  }
})();
