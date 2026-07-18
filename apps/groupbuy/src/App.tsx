// App 外殼：Router（團清單 / 開團 / 填單 / 後台）。
import { Navigate, Route, Routes } from 'react-router-dom';
import { useGroups } from './hooks/useGroups';
import { AppDataProvider } from './AppData';
import { GroupsPage } from './pages/GroupsPage';
import { CreateGroupPage } from './pages/CreateGroupPage';
import { OrderPage } from './pages/OrderPage';
import { DashboardPage } from './pages/DashboardPage';
import { SharePage } from './pages/SharePage';
import { JoinPage } from './pages/JoinPage';

export default function App() {
  const data = useGroups();

  return (
    <AppDataProvider value={data}>
      <div className="app-shell">
        {data.storageError && (
          <p className="banner error" role="alert">
            資料未成功儲存：{data.storageError}
          </p>
        )}
        {data.dataCorrupted && (
          <p className="banner warn" role="alert">
            偵測到本機資料毀損，已丟棄壞掉的部分（必要時已重置）。
            <button className="link" onClick={data.dismissCorruptNotice}>
              知道了
            </button>
          </p>
        )}

        <Routes>
          <Route path="/" element={<GroupsPage />} />
          {/* 買家填單頁：從主揪分享連結進入（獨立動線，無後台入口） */}
          <Route path="/join" element={<JoinPage />} />
          <Route path="/new" element={<CreateGroupPage />} />
          {/* 填單頁：某團的下單畫面（同裝置直接寫入＝主揪代填 / 遞手機填） */}
          <Route path="/groups/:id/order" element={<OrderPage />} />
          {/* 分享頁：產生買家填單連結 + QR */}
          <Route path="/groups/:id/share" element={<SharePage />} />
          {/* 後台頁：某團的累積統計 */}
          <Route path="/groups/:id" element={<DashboardPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </AppDataProvider>
  );
}
