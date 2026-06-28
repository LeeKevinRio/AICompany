import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import App from './App';
import './styles.css';

// 用 HashRouter：本 app 是靜態託管的 PWA，HashRouter 不需伺服器 rewrite，
// 深層連結（如 /sessions/:id）硬重整也不會 404，最適合個人工具部署情境。
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <HashRouter>
      <App />
    </HashRouter>
  </StrictMode>,
);
