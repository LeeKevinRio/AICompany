// 填單頁：選團（由路由 :id 決定）→ 填名字 + 各商品數量 → 送出訂單。
// MVP 定案：同名覆蓋——用相同名字再次送出會覆蓋原本那張單（等同「修改我的單」）。
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAppData } from '../AppData';
import { calcOrderSubtotal } from '../calc/calc';
import { isGroupClosed } from '../deadline';
import { useNow } from '../hooks/useNow';
import { MAX_BUYER_NAME_LENGTH, MAX_ITEM_QTY, MAX_NOTE_LENGTH } from '../types';

export function OrderPage() {
  const { id } = useParams<{ id: string }>();
  const { groups, loaded, submitOrder } = useAppData();
  const navigate = useNavigate();
  const now = useNow();

  const group = groups.find((g) => g.id === id);

  const [buyerName, setBuyerName] = useState('');
  const [note, setNote] = useState('');
  // 商品 id -> 數量。
  const [qtys, setQtys] = useState<Record<string, number>>({});
  const [done, setDone] = useState(false);
  // 【Blocking 修正】submitOrder 可能失敗（例如團在按下送出前的瞬間被截止），
  // 不能無條件顯示「已送出」——失敗時顯示這則訊息，維持在填單畫面而不是假成功畫面。
  const [submitError, setSubmitError] = useState<string | null>(null);

  // 同型問題修正（同 JoinPage）：路由 :id 換成另一團時，React Router 不會 remount 這個
  // 元件（同一個 <Route> 元素、只是 params 不同），若不主動重置會卡在上一團的「已送出」
  // 畫面或殘留上一團填的數量。監聽 id 變化重置本頁表單 state。
  useEffect(() => {
    setBuyerName('');
    setNote('');
    setQtys({});
    setDone(false);
    setSubmitError(null);
  }, [id]);

  function setQty(productId: string, next: number) {
    // NaN 防呆：輸入 '-'、'e' 等會讓 Number() 產生 NaN，直接落 0，
    // 避免 $NaN 與 React controlled input 警告。
    const safe = Number.isFinite(next) ? next : 0;
    const clamped = Math.max(0, Math.min(MAX_ITEM_QTY, Math.floor(safe)));
    setQtys((prev) => ({ ...prev, [productId]: clamped }));
  }

  // 即時試算應付合計。
  const previewTotal = useMemo(() => {
    if (!group) return 0;
    const items = Object.entries(qtys).map(([productId, qty]) => ({ productId, qty }));
    return calcOrderSubtotal({ id: '', buyerName: '', createdAt: 0, items }, group.products);
  }, [group, qtys]);

  if (loaded && !group) {
    return (
      <div>
        <div className="page-header">
          <button className="back" onClick={() => navigate('/')} aria-label="返回">
            ‹
          </button>
          <h1>填單</h1>
        </div>
        <p className="empty">找不到這個團（可能已被刪除）。</p>
      </div>
    );
  }

  if (!group) return <p className="muted">載入中…</p>;

  // 實質截止＝手動 closed 或已過期；擋填單。
  const closed = isGroupClosed(group, now);
  const hasQty = Object.values(qtys).some((q) => q > 0);
  const canSubmit = buyerName.trim() !== '' && hasQty && !closed;

  function handleSubmit() {
    if (!group || !canSubmit) return;
    const items = Object.entries(qtys)
      .map(([productId, qty]) => ({ productId, qty }))
      .filter((i) => i.qty > 0);
    const result = submitOrder(group.id, buyerName, items, note);
    if (!result.ok) {
      // 資料層拒絕寫入（多半是按下送出前的瞬間被截止，或多分頁同步後團已被刪除）：
      // 不能顯示假成功畫面，留在填單畫面並告知原因。
      setSubmitError(
        result.reason === 'closed'
          ? '此團已截止，未送出。請重新整理頁面確認狀態。'
          : '送出失敗，請重新整理頁面再試一次。',
      );
      return;
    }
    setSubmitError(null);
    setDone(true);
  }

  if (done) {
    return (
      <div>
        <div className="page-header">
          <h1>已送出</h1>
        </div>
        <div className="card">
          <p>
            <strong>{buyerName.trim()}</strong> 的訂單已送出。
          </p>
          <p className="total-line">
            <span>應付合計</span>
            <span className="amount tabular">${previewTotal}</span>
          </p>
        </div>
        <button
          className="btn block"
          onClick={() => {
            setBuyerName('');
            setNote('');
            setQtys({});
            setDone(false);
          }}
        >
          再填一張（換人）
        </button>
        <button
          className="btn primary block"
          onClick={() => navigate(`/groups/${group.id}`)}
          style={{ marginTop: 8 }}
        >
          看後台統計
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <button className="back" onClick={() => navigate('/')} aria-label="返回">
          ‹
        </button>
        <h1>{group.name}</h1>
      </div>

      {closed && (
        <p className="banner warn">此團已截止，無法再填單。</p>
      )}
      {submitError && <p className="banner error" role="alert">{submitError}</p>}
      {group.note && <p className="muted">{group.note}</p>}

      <div className="field">
        <label htmlFor="buyer-name">你的名字</label>
        <input
          id="buyer-name"
          type="text"
          value={buyerName}
          maxLength={MAX_BUYER_NAME_LENGTH}
          placeholder="輸入名字（同名會覆蓋原本的單）"
          onChange={(e) => setBuyerName(e.target.value)}
          disabled={closed}
        />
      </div>

      <div className="section-title">選擇數量</div>
      {group.products.map((p) => {
        const qty = qtys[p.id] ?? 0;
        return (
        // 已選（qty > 0）：左側橙色狀態條 + 淡橙底 + 單價轉橙（.product-card.selected）。
        <div key={p.id} className={`product-card card-row ${qty > 0 ? 'selected' : ''}`}>
          {p.image && <img className="product-thumb" src={p.image} alt="" />}
          <div className="grow">
            <div>{p.name}</div>
            <div className="product-price tabular">${p.price}</div>
          </div>
          <div className="stepper">
            <button
              onClick={() => setQty(p.id, qty - 1)}
              disabled={closed || qty <= 0}
              aria-label={`減少 ${p.name}`}
            >
              −
            </button>
            <input
              type="number"
              inputMode="numeric"
              min={0}
              max={MAX_ITEM_QTY}
              value={qty}
              onChange={(e) => setQty(p.id, Number(e.target.value))}
              disabled={closed}
              aria-label={`${p.name} 數量`}
            />
            <button
              className="increment"
              onClick={() => setQty(p.id, qty + 1)}
              disabled={closed}
              aria-label={`增加 ${p.name}`}
            >
              ＋
            </button>
          </div>
        </div>
        );
      })}

      <div className="field" style={{ marginTop: 16 }}>
        <label htmlFor="order-note">備註（可選）</label>
        <input
          id="order-note"
          type="text"
          value={note}
          maxLength={MAX_NOTE_LENGTH}
          placeholder="例：不要辣、少冰"
          onChange={(e) => setNote(e.target.value)}
          disabled={closed}
        />
      </div>

      <p className="total-line">
        <span>應付合計</span>
        <span className="amount tabular">${previewTotal}</span>
      </p>

      <button
        className="btn primary block"
        onClick={handleSubmit}
        disabled={!canSubmit}
        style={{ marginTop: 16 }}
      >
        送出訂單
      </button>
    </div>
  );
}
