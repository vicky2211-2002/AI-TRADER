import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("aiTrader", {
  coreUrl: () => ipcRenderer.invoke("core:url"),
  restartCore: () => ipcRenderer.invoke("core:restart"),
  info: () => ipcRenderer.invoke("app:info"),
  platform: process.platform,
});
