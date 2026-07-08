// App 外殼：Splash → Router（Tab Bar + 路由頁）。
import { useState } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { useSessions } from './hooks/useSessions';
import { AppDataProvider } from './AppData';
import { Splash } from './components/Splash';
import { TabBar } from './components/TabBar';
import { ErrorBoundary } from './components/ErrorBoundary';
import { SessionsPage } from './pages/SessionsPage';
import { SessionDetailPage } from './pages/SessionDetailPage';
import { SettlePage } from './pages/SettlePage';
import { PlayersPage } from './pages/PlayersPage';
import { PlayerDetailPage } from './pages/PlayerDetailPage';
import { SettingsPage } from './pages/SettingsPage';

export default function App() {
  const data = useSessions();
  // Splash 是否仍在畫面上（淡出動畫結束後才卸載）。
  const [splashDone, setSplashDone] = useState(false);

  return (
    <AppDataProvider value={data}>
      {!splashDone && (
        <Splash dataReady={data.loaded} onDone={() => setSplashDone(true)} />
      )}

      <div className="app-shell">
        {data.storageError && (
          <p className="banner error" role="alert" style={{ margin: 16 }}>
            資料未成功儲存：{data.storageError}
          </p>
        )}
        {data.dataCorrupted && (
          <p className="banner warn" role="alert" style={{ margin: 16 }}>
            偵測到本機資料毀損，已丟棄壞掉的部分（必要時已重置）。
            <button className="link" onClick={data.dismissCorruptNotice}>
              知道了
            </button>
          </p>
        )}

        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<SessionsPage />} />
            <Route path="/sessions/:id" element={<SessionDetailPage />} />
            {/* P6 結算頁：全螢幕儀式畫面（自身 fixed 覆蓋，蓋過 TabBar） */}
            <Route path="/sessions/:id/settle" element={<SettlePage />} />
            <Route path="/players" element={<PlayersPage />} />
            {/* 順序依賴：/players/r/:rosterId 必須排在 /players/:name 之前，
                否則 "r" 會被當成 :name 比對到，名冊成員頁無法路由。勿調換這兩行。 */}
            <Route path="/players/r/:rosterId" element={<PlayerDetailPage />} />
            <Route path="/players/:name" element={<PlayerDetailPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </ErrorBoundary>

        <TabBar />
      </div>
    </AppDataProvider>
  );
}
