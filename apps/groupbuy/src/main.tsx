import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import App from './App';
import './styles.css';

// 用 HashRouter：本 app 是靜態託管的網頁工具，HashRouter 不需伺服器 rewrite，
// 深層連結（如 /groups/:id）硬重整也不會 404，最適合個人 / 小工具部署情境。
//
// future flags：提前選用 React Router v7 的行為，消掉開發模式下每頁兩條的 deprecation
// warning，之後升級 v7 也不會再有這批警告要處理。
//   - v7_startTransition：內部狀態更新改包一層 React.startTransition。
//   - v7_relativeSplatPath：修正相對路徑在 splat route（本 app 未使用 splat，無行為影響）下的解析。
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <HashRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <App />
    </HashRouter>
  </StrictMode>,
);
