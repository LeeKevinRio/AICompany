// 首頁：團清單。多團並存，顯示進行中 / 已截止狀態與到期倒數，可進填單或後台。
import { useNavigate } from 'react-router-dom';
import { useAppData } from '../AppData';
import { calcGroupTotal } from '../calc/calc';
import { formatCountdown, isGroupClosed } from '../deadline';
import { useNow } from '../hooks/useNow';

export function GroupsPage() {
  const { groups, loaded, removeGroup } = useAppData();
  const navigate = useNavigate();
  // 每分鐘刷新，讓倒數 / 過期狀態隨時間更新。
  const now = useNow();

  return (
    <div>
      <div className="page-header">
        <h1>團購清單</h1>
        <button className="btn primary" onClick={() => navigate('/new')}>
          ＋ 開團
        </button>
      </div>

      {!loaded && <p className="muted">載入中…</p>}

      {loaded && groups.length === 0 && (
        <p className="empty">
          還沒有任何團購。
          <br />
          點右上角「開團」建立第一個吧。
        </p>
      )}

      {groups.map((g) => {
        // 實質狀態＝手動 closed 或已過期；倒數字串隨截止時間顯示。
        const closed = isGroupClosed(g, now);
        const countdown = formatCountdown(g.deadlineAt, now);
        return (
        // 左側狀態條：進行中橙色 / 已截止暖灰。
        <div key={g.id} className={`card ${closed ? 'status-closed' : 'status-open'}`}>
          <div className="card-row">
            {(() => {
              // 團卡縮圖：取第一個有圖的商品當代表縮圖。
              const cover = g.products.find((p) => p.image)?.image;
              return cover ? <img className="product-thumb" src={cover} alt="" /> : null;
            })()}
            <div className="grow">
              <h2>{g.name}</h2>
              <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                {g.products.length} 項商品・{g.orders.length} 人下單・累積{' '}
                <span className="tabular">${calcGroupTotal(g)}</span>
              </p>
              {g.note && (
                <p className="muted" style={{ margin: '4px 0 0', fontSize: 13 }}>
                  {g.note}
                </p>
              )}
              {countdown && (
                <p
                  className="muted"
                  style={{
                    margin: '4px 0 0',
                    fontSize: 13,
                    color: closed ? 'var(--color-closed)' : 'var(--color-warn)',
                  }}
                >
                  {closed ? '已截止' : `⏰ ${countdown}`}
                </p>
              )}
            </div>
            <span className={`badge ${closed ? 'closed' : 'open'}`}>
              {closed ? '已截止' : '進行中'}
            </span>
          </div>

          <div className="card-row" style={{ marginTop: 12 }}>
            <button
              className="btn primary small grow"
              onClick={() => navigate(`/groups/${g.id}/order`)}
            >
              填單
            </button>
            <button
              className="btn small grow"
              onClick={() => navigate(`/groups/${g.id}`)}
            >
              後台統計
            </button>
            <button
              className="btn danger small"
              onClick={() => {
                if (confirm(`確定刪除「${g.name}」？此動作無法復原。`)) removeGroup(g.id);
              }}
            >
              刪除
            </button>
          </div>
        </div>
        );
      })}
    </div>
  );
}
