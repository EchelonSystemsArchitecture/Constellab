const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("constellab", {
  platform: process.platform,
  versions: process.versions,
});
