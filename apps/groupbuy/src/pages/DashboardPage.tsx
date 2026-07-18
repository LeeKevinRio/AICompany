// 後台頁：某團累積統計——各品項總數量 / 總金額、逐人明細（名字 / 品項 / 小計 / 應付合計）。
import { useNavigate, useParams } from 'react-router-dom';
import { useAppData } from '../AppData';
import { calcBuyerBreakdowns, calcGroupTotal, calcProductTotals } from '../calc/calc';

export function DashboardPage() {
  const { id } = useParams<{ id: string }>();
  const { groups, loaded, toggleClosed, removeOrder } = useAppData();
  const navigate = useNavigate();

  const group = groups.find((g) => g.id === id);

  if (loaded && !group) {
    return (
      <div>
        <div className="page-header">
          <button className="back" onClick={() => navigate('/')} aria-label="返回">
            ‹
          </button>
          <h1>後台統計</h1>
        </div>
        <p className="empty">找不到這個團（可能已被刪除）。</p>
      </div>
    );
  }

  if (!group) return <p className="muted">載入中…</p>;

  const productTotals = calcProductTotals(group);
  const buyers = calcBuyerBreakdowns(group);
  const grandTotal = calcGroupTotal(group);

  return (
    <div>
      <div className="page-header">
        <button className="back" onClick={() => navigate('/')} aria-label="返回">
          ‹
        </button>
        <h1>{group.name}</h1>
        <span className={`badge ${group.closed ? 'closed' : 'open'}`}>
          {group.closed ? '已截止' : '進行中'}
        </span>
      </div>

      {/* 分享入口：方案 C 的核心動線——開完團第一個下一步就是把連結分享出去。 */}
      <button
        className="btn primary block"
        onClick={() => navigate(`/groups/${group.id}/share`)}
        style={{ marginBottom: 12 }}
      >
        邀請填單（分享連結 / QR）
      </button>

      <div className="card-row" style={{ marginBottom: 16 }}>
        <button
          className="btn small grow"
          onClick={() => navigate(`/groups/${group.id}/order`)}
        >
          現場代填
        </button>
        <button className="btn small grow" onClick={() => toggleClosed(group.id)}>
          {group.closed ? '重新開團' : '結單截止'}
        </button>
      </div>

      {/* 各品項累積 */}
      <div className="section-title">各品項累積</div>
      <div className="card">
        <table className="stat-table tabular">
          <thead>
            <tr>
              <th>商品</th>
              <th className="num">單價</th>
              <th className="num">數量</th>
              <th className="num">小計</th>
            </tr>
          </thead>
          <tbody>
            {productTotals.map((pt) => (
              <tr key={pt.productId}>
                <td>{pt.name}</td>
                <td className="num">${pt.price}</td>
                <td className="num">{pt.qty}</td>
                <td className="num amount">${pt.amount}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={3}>總金額</td>
              <td className="num amount">${grandTotal}</td>
            </tr>
          </tfoot>
        </table>
      </div>

      {/* 逐人明細 */}
      <div className="section-title">逐人明細（{buyers.length} 人）</div>
      {buyers.length === 0 && <p className="empty">還沒有人下單。</p>}
      {buyers.map((b) => {
        const order = group.orders.find((o) => o.buyerName === b.buyerName);
        return (
          <div key={b.buyerName} className="card">
            <div className="card-row">
              <h3 className="grow">{b.buyerName}</h3>
              <span
                className="tabular"
                style={{ color: 'var(--color-amount)', fontWeight: 600 }}
              >
                ${b.total}
              </span>
            </div>
            <ul className="muted" style={{ margin: '8px 0 0', paddingLeft: 18, fontSize: 14 }}>
              {b.lines.map((l) => (
                <li key={l.productId} className="tabular">
                  {l.name} ×{l.qty} = ${l.subtotal}
                </li>
              ))}
            </ul>
            {order && (
              <button
                className="btn danger small"
                style={{ marginTop: 8 }}
                onClick={() => {
                  if (confirm(`刪除 ${b.buyerName} 的訂單？`)) removeOrder(group.id, order.id);
                }}
              >
                刪除此人訂單
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
