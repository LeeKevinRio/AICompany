// 底部頁籤（視覺規範第 6 節）。毛玻璃、選中態 pill、56px + safe area。
import { useLocation, useNavigate } from 'react-router-dom';
import { IconSessions, IconPlayers, IconSettings } from './icons';

interface TabDef {
  label: string;
  path: string;
  // 判斷此 tab 是否為 active 的路徑前綴
  match: (pathname: string) => boolean;
  Icon: typeof IconSessions;
}

const TABS: TabDef[] = [
  {
    label: '牌局',
    path: '/',
    match: (p) => p === '/' || p.startsWith('/sessions'),
    Icon: IconSessions,
  },
  {
    label: '玩家',
    path: '/players',
    match: (p) => p.startsWith('/players'),
    Icon: IconPlayers,
  },
  {
    label: '設定',
    path: '/settings',
    match: (p) => p.startsWith('/settings'),
    Icon: IconSettings,
  },
];

export function TabBar() {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  return (
    <nav className="tab-bar">
      {TABS.map((tab) => {
        const active = tab.match(pathname);
        return (
          <button
            key={tab.path}
            className={`tab-item${active ? ' active' : ''}`}
            onClick={() => navigate(tab.path)}
          >
            <tab.Icon />
            <span>{tab.label}</span>
            <span className="tab-pill" />
          </button>
        );
      })}
    </nav>
  );
}
