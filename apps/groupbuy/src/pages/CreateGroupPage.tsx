// 開團頁：建立團購（團名、截止註記、商品清單：名稱 + 單價，可增刪）。
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppData } from '../AppData';
import type { NewProduct } from '../hooks/useGroups';
import { MAX_GROUP_NAME_LENGTH, MAX_PRODUCT_NAME_LENGTH } from '../types';

/** 商品編輯列的暫存型別：price 用字串以保留輸入中的空白 / 半形狀態。 */
interface DraftProduct {
  name: string;
  price: string;
}

function emptyProduct(): DraftProduct {
  return { name: '', price: '' };
}

export function CreateGroupPage() {
  const { addGroup } = useAppData();
  const navigate = useNavigate();

  const [name, setName] = useState('');
  const [note, setNote] = useState('');
  // datetime-local 的值是主揪當地牆上時間字串（如 "2026-07-20T20:00"，無時區）。
  const [deadline, setDeadline] = useState('');
  const [products, setProducts] = useState<DraftProduct[]>([emptyProduct()]);

  function updateProduct(index: number, patch: Partial<DraftProduct>) {
    setProducts((prev) => prev.map((p, i) => (i === index ? { ...p, ...patch } : p)));
  }

  function addRow() {
    setProducts((prev) => [...prev, emptyProduct()]);
  }

  function removeRow(index: number) {
    setProducts((prev) => prev.filter((_, i) => i !== index));
  }

  // 至少要有一個有效商品（名稱非空）才能開團。
  const validProducts = products.filter((p) => p.name.trim() !== '');
  const canSubmit = validProducts.length > 0;

  function handleSubmit() {
    if (!canSubmit) return;
    const payload: NewProduct[] = validProducts.map((p) => ({
      name: p.name,
      price: Number(p.price) || 0,
    }));
    // datetime-local → epoch 毫秒（new Date 以主揪當地時區解讀，存絕對時間點）；
    // 空字串或解析失敗（NaN）→ 不設截止時間。
    const ts = deadline ? new Date(deadline).getTime() : NaN;
    const deadlineAt = Number.isFinite(ts) ? ts : undefined;
    const id = addGroup(name, note, payload, deadlineAt);
    // 開完團直接進後台，方便主揪把填單連結分享出去 / 檢視。
    navigate(`/groups/${id}`, { replace: true });
  }

  return (
    <div>
      <div className="page-header">
        <button className="back" onClick={() => navigate('/')} aria-label="返回">
          ‹
        </button>
        <h1>開團</h1>
      </div>

      <div className="field">
        <label htmlFor="group-name">團名</label>
        <input
          id="group-name"
          type="text"
          value={name}
          maxLength={MAX_GROUP_NAME_LENGTH}
          placeholder="例：週五下午茶團"
          onChange={(e) => setName(e.target.value)}
        />
      </div>

      <div className="field">
        <label htmlFor="group-note">截止註記（可選）</label>
        <input
          id="group-note"
          type="text"
          value={note}
          placeholder="例：7/20 晚上 8 點截止"
          onChange={(e) => setNote(e.target.value)}
        />
      </div>

      <div className="field">
        <label htmlFor="group-deadline">截止時間（可選，到時自動截止）</label>
        <input
          id="group-deadline"
          type="datetime-local"
          value={deadline}
          onChange={(e) => setDeadline(e.target.value)}
        />
      </div>

      <div className="section-title">商品清單</div>
      {products.map((p, i) => (
        <div key={i} className="line">
          <input
            className="name"
            type="text"
            value={p.name}
            maxLength={MAX_PRODUCT_NAME_LENGTH}
            placeholder="商品名稱"
            onChange={(e) => updateProduct(i, { name: e.target.value })}
          />
          <input
            className="price"
            type="number"
            inputMode="numeric"
            min={0}
            value={p.price}
            placeholder="單價"
            onChange={(e) => updateProduct(i, { price: e.target.value })}
          />
          <button
            className="btn danger small"
            onClick={() => removeRow(i)}
            disabled={products.length === 1}
            aria-label="移除商品"
          >
            ✕
          </button>
        </div>
      ))}

      <button className="btn ghost-primary block" onClick={addRow} style={{ marginTop: 8 }}>
        ＋ 新增商品
      </button>

      <button
        className="btn primary block"
        onClick={handleSubmit}
        disabled={!canSubmit}
        style={{ marginTop: 24 }}
      >
        建立團購
      </button>
      {!canSubmit && <p className="muted" style={{ textAlign: 'center' }}>至少新增一項有名稱的商品</p>}
    </div>
  );
}
