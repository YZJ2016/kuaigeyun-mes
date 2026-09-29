const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('stationSetup', {
  saveServerOrigin(origin) {
    return ipcRenderer.invoke('stationSetup:saveServerOrigin', origin);
  },
});
