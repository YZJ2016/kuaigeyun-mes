const form = document.getElementById('form');
const input = document.getElementById('origin');
const button = document.getElementById('save');
const status = document.getElementById('status');

function setStatus(text, kind) {
  status.textContent = text;
  status.className = kind || '';
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!window.stationSetup || typeof window.stationSetup.saveServerOrigin !== 'function') {
    setStatus('配置接口不可用', 'error');
    return;
  }
  button.disabled = true;
  setStatus('正在连接…', '');
  try {
    const result = await window.stationSetup.saveServerOrigin(input.value);
    if (!result || !result.ok) {
      setStatus((result && result.message) || '保存失败', 'error');
      button.disabled = false;
      return;
    }
    setStatus('已保存，正在打开工位…', 'ok');
  } catch {
    setStatus('保存失败', 'error');
    button.disabled = false;
  }
});
