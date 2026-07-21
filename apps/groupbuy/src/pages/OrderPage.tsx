// 填單頁：選團（由路由 :id 決定）→ 填名字 + 各商品數量 → 送出訂單。
// MVP 定案：同名覆蓋——用相同名字再次送出會覆蓋原本那張單（等同「修改我的單」）。
import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAppData } from '../AppData';
import { calcOrderSubtotal } from '../calc/calc';
import { isGroupClosed } from '../deadline';
import { useNow } from '../hooks/useNow';
import { MAX_BUYER_NAME_LENGTH, MAX_ITEM_QTY } from '../types';

export function OrderPage() {
  const { id } = useParams<{ id: string }>();
  const { groups, loaded, submitOrder } = useAppData();
  const navigate = useNavigate();
  const now = useNow();

  const group = groups.find((g) => g.id === id);

  const [buyerName, setBuyerName] = useState('');
  // 商品 id -> 數量。
  const [qtys, setQtys] = useState<Record<string, number>>({});
  const [done, setDone] = useState(false);

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
    submitOrder(group.id, buyerName, items);
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
