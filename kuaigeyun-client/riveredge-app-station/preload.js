const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('stationShell', {
  setWorkstationId(id) {
    return ipcRenderer.invoke('stationShell:setWorkstationId', id);
  },
  getWorkstationId() {
    return ipcRenderer.invoke('stationShell:getWorkstationId');
  },
  notifyStationRejected() {
    return ipcRenderer.invoke('stationShell:stationRejected');
  },
});
