import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// A tab can outlive a deployment and still reference the previous page chunks.
// Refresh once; persistent network failures fall through to the route error UI.
window.addEventListener('vite:preloadError', () => {
  if (!navigator.onLine) return
  try {
    const key = 'agentcy:chunk-reload'
    const lastReload = Number(sessionStorage.getItem(key) || 0)
    if (Date.now() - lastReload < 60000) return
    sessionStorage.setItem(key, String(Date.now()))
  } catch { return } // Storage restrictions must not cause a reload loop.
  window.location.reload()
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
