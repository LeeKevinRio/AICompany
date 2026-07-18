// 買家填單頁（方案 C）：從主揪分享的連結進入，解析 URL 還原團定義，填單後產生「回單碼」。
//
// 隔離原則：本頁完全獨立於主揪後台——不讀 / 不寫主揪的 localStorage、沒有任何連回 app 首頁或
// 後台的入口、看不到其他買家明細。買家送出後不寫任何資料，只拿到一段回單碼貼回 LINE 給主揪。
// D3 定案：不做買家返回修改（填錯找主揪）。
import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { decodeGroupPayload } from '../share/groupCodec';
import { encodeReceipt } from '../share/receiptCodec';
import { calcOrderSubtotal } from '../calc/calc';
import { MAX_BUYER_NAME_LENGTH, MAX_ITEM_QTY, type OrderItem } from '../types';

export function JoinPage() {
  const [searchParams] = useSearchParams();
  const payload = searchParams.get('d');

  // 解析團定義（壞連結 → null）。
  const def = useMemo(() => (payload ? decodeGroupPayload(payload) : null), [payload]);

  const [buyerName, setBuyerName] = useState('');
  const [note, setNote] = useState('');
  const [qtys, setQtys] = useState<Record<string, number>>({});
  const [receipt, setReceipt] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  function setQty(productId: string, next: number) {
    const safe = Number.isFinite(next) ? next : 0;
    const clamped = Math.max(0, Math.min(MAX_ITEM_QTY, Math.floor(safe)));
    setQtys((prev) => ({ ...prev, [productId]: clamped }));
  }

  const items: OrderItem[] = useMemo(
    () =>
      Object.entries(qtys)
        .map(([productId, qty]) => ({ productId, qty }))
        .filter((i) => i.qty > 0),
    [qtys],
  );

  const previewTotal = useMemo(
    () => (def ? calcOrderSubtotal({ id: '', buyerName: '', createdAt: 0, items }, def.products) : 0),
    [def, items],
  );

  // 壞連結 / 缺參數：友善錯誤，不 crash。
  if (!def) {
    return (
      <div>
        <div className="page-header">
          <h1>填單連結無效</h1>
        </div>
        <p className="empty">
          這個填單連結讀不到內容（可能已損毀或不完整）。
          <br />
          請向主揪索取新的填單連結。
        </p>
      </div>
    );
  }

  const canSubmit = buyerName.trim() !== '' && items.length > 0;

  function handleSubmit() {
    if (!def || !canSubmit) return;
    setReceipt(
      encodeReceipt({
        groupId: def.groupId,
        buyerName: buyerName.trim(),
        items,
        ...(note.trim() ? { note: note.trim() } : {}),
      }),
    );
  }

  async function handleCopy() {
    if (!receipt) return;
    try {
      await navigator.clipboard.writeText(receipt);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      alert('無法自動複製，請長按上方回單碼手動複製。');
    }
  }

  // 訂單確認頁（送出後停留）：買家的收據，截圖 / 貼回 LINE 用。
  if (receipt) {
    return (
      <div>
        <div className="page-header">
          <h1>訂單已送出</h1>
        </div>
        <div className="card">
          <p>
            <strong>{buyerName.trim()}</strong> 的訂單（{def.name}）
          </p>
          <ul className="muted" style={{ margin: '8px 0', paddingLeft: 18, fontSize: 14 }}>
            {items.map((i) => {
              const p = def.products.find((pp) => pp.id === i.productId);
              if (!p) return null;
              return (
                <li key={i.productId} className="tabular">
                  {p.name} ×{i.qty} = ${p.price * i.qty}
                </li>
              );
            })}
          </ul>
          <p className="total-line">
            <span>應付合計</span>
            <span className="amount tabular">${previewTotal}</span>
          </p>
        </div>

        <div className="section-title">你的回單碼</div>
        <p className="muted" style={{ fontSize: 13 }}>
          把這段回單碼整段複製、貼回 LINE 傳給主揪，主揪就會收到你的訂單。
        </p>
        <div className="receipt-code">{receipt}</div>
        <button className="btn primary block" onClick={handleCopy}>
          {copied ? '已複製回單碼 ✓' : '複製回單碼'}
        </button>
        <p className="muted" style={{ fontSize: 13, textAlign: 'center', marginTop: 12 }}>
          小提醒：可截圖這一頁留存。填錯了請直接找主揪處理。
        </p>
      </div>
    );
  }

  // 填單頁
  return (
    <div>
      <div className="page-header">
        <h1>{def.name}</h1>
      </div>
      {def.note && <p className="muted">{def.note}</p>}

      <div className="field">
        <label htmlFor="buyer-name">你的名字</label>
        <input
          id="buyer-name"
          type="text"
          value={buyerName}
          maxLength={MAX_BUYER_NAME_LENGTH}
          placeholder="輸入名字"
          onChange={(e) => setBuyerName(e.target.value)}
        />
      </div>

      <div className="section-title">選擇數量</div>
      {def.products.map((p) => {
        const qty = qtys[p.id] ?? 0;
        return (
          <div key={p.id} className={`product-card card-row ${qty > 0 ? 'selected' : ''}`}>
            <div className="grow">
              <div>{p.name}</div>
              <div className="product-price tabular">${p.price}</div>
            </div>
            <div className="stepper">
              <button
                onClick={() => setQty(p.id, qty - 1)}
                disabled={qty <= 0}
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
                aria-label={`${p.name} 數量`}
              />
              <button
                className="increment"
                onClick={() => setQty(p.id, qty + 1)}
                aria-label={`增加 ${p.name}`}
              >
                ＋
              </button>
            </div>
          </div>
        );
      })}

      <div className="field" style={{ marginTop: 16 }}>
        <label htmlFor="buyer-note">備註（可選）</label>
        <input
          id="buyer-note"
          type="text"
          value={note}
          placeholder="例：不要辣、少冰"
          onChange={(e) => setNote(e.target.value)}
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
