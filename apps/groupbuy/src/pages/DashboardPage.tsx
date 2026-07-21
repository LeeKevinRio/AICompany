// 後台頁：某團累積統計——各品項總數量 / 總金額、逐人明細（名字 / 品項 / 小計 / 應付合計）。
// 批次三：整合買家回單匯入（貼上回單碼）＋同裝置代填（現場代填），統計照常聚合。
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAppData } from '../AppData';
import {
  calcBuyerBreakdowns,
  calcGroupTotal,
  calcProductTotals,
  calcUnpaidTotal,
} from '../calc/calc';
import { decodeReceipt } from '../share/receiptCodec';
import { formatCountdown, isGroupClosed } from '../deadline';
import { useNow } from '../hooks/useNow';

export function DashboardPage() {
  const { id } = useParams<{ id: string }>();
  const { groups, loaded, toggleClosed, removeOrder, submitOrder, togglePaid } =
    useAppData();
  const navigate = useNavigate();
  const now = useNow();

  // 回單碼匯入的暫存輸入與結果訊息。
  const [receiptText, setReceiptText] = useState('');
  const [importMsg, setImportMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(
    null,
  );
  // 剛按下「已收」的那一列名字：套 .row-flash 短暫閃光，動畫結束即清掉（reduced-motion 下 CSS 自動停用）。
  const [flashName, setFlashName] = useState<string | null>(null);

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
  const unpaidTotal = calcUnpaidTotal(group);
  // 有訂單且未收款歸零 → 結清（完成感：summary 那格轉綠 + 已結清 badge）。
  const settled = buyers.length > 0 && unpaidTotal === 0;
  // 實質截止＝手動 closed 或已過期；倒數 / 截止顯示與收單擋門都看這個。
  const closed = isGroupClosed(group, now);
  const countdown = formatCountdown(group.deadlineAt, now);

  // 按「已收 / 取消已收」：切換狀態；由未收→已收時觸發該列閃光。
  function handleTogglePaid(orderId: string, buyerName: string, willPay: boolean) {
    if (!group) return; // 閉包內重新 narrow
    togglePaid(group.id, orderId);
    if (willPay) {
      setFlashName(buyerName);
      window.setTimeout(() => setFlashName(null), 600);
    }
  }

  // 匯入買家貼回的回單碼：解碼 → 驗團別 → 寫入本團（同名覆蓋，沿用 submitOrder）。
  function handleImport() {
    if (!group) return; // 閉包內重新 narrow（TS 不會把外層 guard 帶進巢狀函式）
    const parsed = decodeReceipt(receiptText);
    if (!parsed) {
      setImportMsg({ kind: 'err', text: '讀不到有效的回單碼，請確認整段完整貼上。' });
      return;
    }
    if (parsed.groupId !== group.id) {
      setImportMsg({ kind: 'err', text: '這張回單不屬於本團（團別不符）。' });
      return;
    }
    if (parsed.items.length === 0) {
      setImportMsg({ kind: 'err', text: '這張回單沒有任何品項。' });
      return;
    }
    if (isGroupClosed(group, Date.now())) {
      setImportMsg({
        kind: 'err',
        text: group.closed
          ? '本團已截止，請先「重新開團」再匯入。'
          : '本團已過截止時間，請先「重新開團」再匯入。',
      });
      return;
    }
    submitOrder(group.id, parsed.buyerName, parsed.items);
    setReceiptText('');
    setImportMsg({
      kind: 'ok',
      text: `已收單：${parsed.buyerName}（同名會覆蓋原本的單）。`,
    });
  }

  return (
    <div>
      <div className="page-header">
        <button className="back" onClick={() => navigate('/')} aria-label="返回">
          ‹
        </button>
        <h1>{group.name}</h1>
        <span className={`badge ${closed ? 'closed' : 'open'}`}>
          {closed ? '已截止' : '進行中'}
        </span>
      </div>

      {group.deadlineAt !== undefined && (
        <p
          className="muted"
          style={{
            marginTop: -8,
            fontSize: 13,
            color: closed ? 'var(--color-closed)' : 'var(--color-warn)',
          }}
        >
          {closed
            ? `已於 ${new Date(group.deadlineAt).toLocaleString('zh-TW')} 截止`
            : `⏰ ${countdown}（${new Date(group.deadlineAt).toLocaleString('zh-TW')} 截止）`}
        </p>
      )}

      {/* 頂部摘要：訂單數 / 總金額 / 未收款（未收 >0 紅、歸零轉綠並顯示已結清）。 */}
      <div className="summary-block">
        <div className="summary-stat">
          <span className="stat-number">{buyers.length}</span>
          <span className="stat-label">訂單數</span>
        </div>
        <div className="summary-stat">
          <span className="stat-number is-amount">${grandTotal}</span>
          <span className="stat-label">總金額</span>
        </div>
        <div className="summary-stat">
          <span className={`stat-number ${settled ? 'is-clear' : 'is-unpaid'}`}>
            ${unpaidTotal}
          </span>
          <span className="stat-label">
            {settled ? '已收齊' : '未收款'}
            {settled && <span className="badge settled" style={{ marginLeft: 6 }}>已結清</span>}
          </span>
        </div>
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

      {/* 收單：貼上買家從 LINE 傳回的回單碼 → 匯入本團統計 */}
      <div className="section-title">貼上回單碼收單</div>
      <div className="card">
        <textarea
          rows={2}
          value={receiptText}
          placeholder="把買家傳回的回單碼（GBR1.… 開頭）整段貼在這裡"
          onChange={(e) => {
            setReceiptText(e.target.value);
            if (importMsg) setImportMsg(null);
          }}
        />
        <button
          className="btn primary block"
          onClick={handleImport}
          disabled={receiptText.trim() === ''}
          style={{ marginTop: 8 }}
        >
          匯入這張回單
        </button>
        {importMsg && (
          <p
            className={`banner ${importMsg.kind === 'ok' ? 'success' : 'error'}`}
            role="status"
            style={{ marginTop: 8, marginBottom: 0 }}
          >
            {importMsg.text}
          </p>
        )}
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
        const paid = order?.paid ?? false;
        return (
          <div key={b.buyerName} className="card">
            {/* 收款主列：規範 .member-row / .is-paid（已收 → 名字轉灰、金額刪除線）。 */}
            <div
              className={`member-row ${paid ? 'is-paid' : ''} ${
                flashName === b.buyerName ? 'row-flash' : ''
              }`}
              style={{ borderBottom: 'none' }}
            >
              <span className="member-name">{b.buyerName}</span>
              <span className="member-amount tabular">${b.total}</span>
              {order && (
                <button
                  className={`btn small ${paid ? '' : 'success'}`}
                  onClick={() => handleTogglePaid(order.id, b.buyerName, !paid)}
                  aria-pressed={paid}
                >
                  {paid ? (
                    <>
                      <span className="check-pop" aria-hidden="true">
                        ✓
                      </span>{' '}
                      已收
                    </>
                  ) : (
                    '標記已收'
                  )}
                </button>
              )}
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
