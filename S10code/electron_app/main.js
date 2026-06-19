// Minimal Electron main process for the Session 10 computer-use demo.
// Launched as:  electron . --remote-debugging-port=<port>
// The single BrowserWindow renderer (index.html) is exposed over CDP, so the
// computer_use skill can attach with Playwright's connect_over_cdp and drive
// the page (type into #editor, read it back) — the Electron debug-port path.
const { app, BrowserWindow } = require('electron')

function createWindow() {
  const win = new BrowserWindow({
    width: 900,
    height: 600,
    title: 'S10 Computer-Use Electron Demo',
    webPreferences: { contextIsolation: true },
  })
  win.loadFile('index.html')
}

app.whenReady().then(() => {
  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  // Quit when the agent closes the window, so no instance lingers between runs.
  if (process.platform !== 'darwin') app.quit()
})
