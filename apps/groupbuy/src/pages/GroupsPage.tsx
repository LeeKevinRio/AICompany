// 首頁：團清單。多團並存，顯示進行中 / 已截止狀態，可進填單或後台。
import { useNavigate } from 'react-router-dom';
import { useAppData } from '../AppData';
import { calcGroupTotal } from '../calc/calc';

export function GroupsPage() {
  const { groups, loaded, removeGroup } = useAppData();
  const navigate = useNavigate();

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

      {groups.map((g) => (
        <div key={g.id} className="card">
          <div className="card-row">
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
            </div>
            <span className={`badge ${g.closed ? 'closed' : 'open'}`}>
              {g.closed ? '已截止' : '進行中'}
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
      ))}
    </div>
  );
}
