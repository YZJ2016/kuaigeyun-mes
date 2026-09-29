const { app, BrowserWindow, Menu, ipcMain, net, powerSaveBlocker } = require('electron');
const fs = require('fs');
const path = require('path');

const STATION_PATH = '/apps/kuaizhizao/production-execution/station';
const CONFIG_NAME = 'station-shell.json';
const REACH_TIMEOUT_MS = 10000;

function configFilePath() {
  return path.join(app.getPath('userData'), CONFIG_NAME);
}

function readConfig() {
  try {
    const data = JSON.parse(fs.readFileSync(configFilePath(), 'utf8'));
    if (!data || typeof data !== 'object' || Array.isArray(data)) return {};
    return data;
  } catch {
    return {};
  }
}

function writeConfig(next) {
  const file = configFilePath();
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `${JSON.stringify(next, null, 2)}\n`, 'utf8');
}

function normalizeOrigin(raw) {
  if (typeof raw !== 'string') return '';
  const text = raw.trim();
  if (!text) return '';
  let url;
  try {
    url = new URL(text);
  } catch {
    return '';
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return '';
  if (url.username || url.password) return '';
  return url.origin;
}

function serverOrigin(config) {
  const fromEnv = normalizeOrigin(process.env.STATION_SERVER_ORIGIN);
  if (fromEnv) return fromEnv;
  return normalizeOrigin(config.serverOrigin);
}

function parseOriginInput(raw) {
  if (typeof raw !== 'string' || !raw.trim()) {
    return { error: '请填写服务器地址' };
  }
  let url;
  try {
    url = new URL(raw.trim());
  } catch {
    return { error: '地址格式不正确，请以 http:// 或 https:// 开头' };
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    return { error: '只支持 http 或 https' };
  }
  if (url.username || url.password) {
    return { error: '不要在地址里填写用户名或口令' };
  }
  if ((url.pathname && url.pathname !== '/') || url.search || url.hash) {
    return { error: '只填写服务器地址，不要带路径或参数' };
  }
  return { origin: url.origin };
}

function connectionErrorMessage(err) {
  const text = String((err && err.message) || '');
  if (err && (err.name === 'TimeoutError' || err.name === 'AbortError')) {
    return '连接超时，请检查地址和网络';
  }
  if (/ERR_TIMED_OUT|ERR_CONNECTION_TIMED_OUT/i.test(text)) {
    return '连接超时，请检查地址和网络';
  }
  if (/ERR_NAME_NOT_RESOLVED|ENOTFOUND/i.test(text)) {
    return '找不到该服务器，请检查地址';
  }
  if (/ERR_CONNECTION_REFUSED|ECONNREFUSED/i.test(text)) {
    return '服务器拒绝连接，请检查地址和端口';
  }
  if (/CERT_|ERR_CERT/i.test(text)) {
    return '服务器证书不受信任';
  }
  return '无法连接服务器，请检查地址和网络';
}

async function assertStationReachable(origin) {
  const target = stationUrl(origin, '');
  let response;
  try {
    response = await net.fetch(target, {
      method: 'GET',
      redirect: 'follow',
      signal: AbortSignal.timeout(REACH_TIMEOUT_MS),
    });
  } catch (err) {
    throw new Error(connectionErrorMessage(err));
  }
  try {
    if (response.body) await response.body.cancel();
  } catch {
    // 丢弃响应体失败不影响连通性判断
  }
  if (response.status === 404) {
    throw new Error('已连上服务器，但工位入口不存在');
  }
  if (response.status >= 500) {
    throw new Error(`服务器暂时无法访问（HTTP ${response.status}）`);
  }
}

function normalizeWorkstationId(id) {
  if (typeof id === 'number') {
    if (!Number.isFinite(id)) return null;
    id = String(id);
  }
  if (typeof id !== 'string') return null;
  const text = id.trim();
  if (!text || text.length > 128) return null;
  if (/[\u0000-\u001F\u007F]/.test(text)) return null;
  return text;
}

function stationUrl(origin, workstationId) {
  const url = new URL(STATION_PATH, origin);
  url.searchParams.set('workstationId', workstationId || '');
  return url.toString();
}

function enableLoginItem() {
  const settings = { openAtLogin: true };
  if (!app.isPackaged) {
    settings.path = process.execPath;
    settings.args = [app.getAppPath()];
  }
  app.setLoginItemSettings(settings);
}

function createWindow(origin, workstationId) {
  const win = new BrowserWindow({
    fullscreen: true,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      backgroundThrottling: false,
    },
  });
  win.setMenu(null);
  win.loadURL(stationUrl(origin, workstationId));
  return win;
}

function openSetupWindow() {
  const win = new BrowserWindow({
    fullscreen: true,
    autoHideMenuBar: true,
    backgroundColor: '#f3f4f6',
    webPreferences: {
      preload: path.join(__dirname, 'setup-preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      backgroundThrottling: false,
    },
  });
  win.setMenu(null);
  win.loadFile(path.join(__dirname, 'setup.html'));
  return win;
}

app.whenReady().then(() => {
  Menu.setApplicationMenu(null);
  powerSaveBlocker.start('prevent-display-sleep');
  enableLoginItem();

  ipcMain.handle('stationShell:setWorkstationId', (_event, id) => {
    const workstationId = normalizeWorkstationId(id);
    if (!workstationId) {
      throw new Error('workstation id required');
    }
    const current = readConfig();
    writeConfig({
      serverOrigin: typeof current.serverOrigin === 'string' ? current.serverOrigin : '',
      workstationId,
    });
    return workstationId;
  });

  ipcMain.handle('stationShell:getWorkstationId', () => {
    return normalizeWorkstationId(readConfig().workstationId);
  });

  let savingOrigin = false;
  ipcMain.handle('stationSetup:saveServerOrigin', async (event, raw) => {
    if (savingOrigin) return { ok: false, message: '正在测试，请稍候' };
    const parsed = parseOriginInput(raw);
    if (parsed.error) return { ok: false, message: parsed.error };
    savingOrigin = true;
    try {
      await assertStationReachable(parsed.origin);
      const current = readConfig();
      const workstationId = typeof current.workstationId === 'string' ? current.workstationId : '';
      try {
        writeConfig({ serverOrigin: parsed.origin, workstationId });
      } catch {
        return { ok: false, message: '无法写入本机配置' };
      }
      createWindow(parsed.origin, normalizeWorkstationId(workstationId) || '');
      const setupWin = BrowserWindow.fromWebContents(event.sender);
      if (setupWin && !setupWin.isDestroyed()) setupWin.close();
      return { ok: true };
    } catch (err) {
      return { ok: false, message: err instanceof Error ? err.message : '无法连接服务器，请检查地址和网络' };
    } finally {
      savingOrigin = false;
    }
  });

  const config = readConfig();
  const origin = serverOrigin(config);
  if (!origin) {
    openSetupWindow();
    return;
  }
  const workstationId = normalizeWorkstationId(config.workstationId) || '';
  createWindow(origin, workstationId);
});

app.on('window-all-closed', () => {
  app.quit();
});
