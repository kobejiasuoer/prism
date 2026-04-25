(function () {
  const root = document.querySelector('[data-parameter-root]');
  if (!root) return;

  const form = root.querySelector('[data-parameter-editor]');
  const textarea = root.querySelector('[data-parameter-editor-input]');
  const feedback = root.querySelector('[data-parameter-feedback]');
  const resetButton = root.querySelector('[data-parameter-reset]');
  const saveButton = root.querySelector('[data-parameter-save]');
  const loadUrl = root.getAttribute('data-parameter-load-url');
  const saveUrl = root.getAttribute('data-parameter-save-url');

  if (!form || !textarea || !feedback || !resetButton || !saveButton || !loadUrl || !saveUrl) {
    return;
  }

  function setBusy(busy) {
    form.dataset.busy = busy ? 'true' : 'false';
    textarea.disabled = busy;
    resetButton.disabled = busy;
    saveButton.disabled = busy;
  }

  function setFeedback(message) {
    feedback.textContent = message;
  }

  async function loadLatest(message) {
    setBusy(true);
    try {
      const response = await fetch(loadUrl, {
        headers: {
          Accept: 'application/json',
        },
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || '读取参数失败。');
      }
      textarea.value = payload.raw_json || '';
      setFeedback(message || '已重新载入磁盘版本。');
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : '读取参数失败。');
    } finally {
      setBusy(false);
    }
  }

  resetButton.addEventListener('click', function () {
    loadLatest();
  });

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    setBusy(true);
    setFeedback('正在校验并保存参数...');

    try {
      const response = await fetch(saveUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        body: JSON.stringify({
          raw_json: textarea.value,
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || '保存失败。');
      }

      textarea.value = (payload.parameters && payload.parameters.raw_json) || textarea.value;
      setFeedback((payload.message || '保存成功。') + ' 页面即将刷新。');
      window.setTimeout(function () {
        window.location.reload();
      }, 400);
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : '保存失败。');
      setBusy(false);
    }
  });
})();
