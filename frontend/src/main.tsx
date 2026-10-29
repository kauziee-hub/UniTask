import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

try {
  const saved = localStorage.getItem('unitask.theme')
  if (saved === 'light' || saved === 'dark') document.documentElement.dataset.theme = saved
} catch {
  // Storage unavailable; follow the system theme.
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
