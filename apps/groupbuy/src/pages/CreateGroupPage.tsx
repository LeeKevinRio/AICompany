// 開團頁：建立團購（團名、截止註記 / 時間、商品清單：名稱 + 單價 + 可選圖片，可增刪）。
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppData } from '../AppData';
import type { NewProduct } from '../hooks/useGroups';
import { MAX_GROUP_NAME_LENGTH, MAX_PRODUCT_NAME_LENGTH } from '../types';
import {
  compressImageToDataUrl,
  estimateDataUrlBytes,
  estimateGroupsBytes,
  IMAGE_MAX_BYTES,
  STORAGE_WARN_BYTES,
} from '../image';

/** 商品編輯列的暫存型別：price 用字串以保留輸入中的空白 / 半形狀態。 */
interface DraftProduct {
  name: string;
  price: string;
  image?: string; // 壓縮後的 JPEG data URL
}

function emptyProduct(): DraftProduct {
  return { name: '', price: '' };
}

/** 把 Date 轉成 datetime-local input 需要的當地時間字串（YYYY-MM-DDTHH:mm）。 */
function toLocalDatetimeInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}`;
}

export function CreateGroupPage() {
  const { addGroup, groups } = useAppData();
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

  // 選圖：壓縮 → 檢查單張上限 → 存進該列草稿。錯誤以 alert 提示，不 crash。
  async function handlePickImage(index: number, file: File | undefined) {
    if (!file) return;
    try {
      const dataUrl = await compressImageToDataUrl(file);
      if (estimateDataUrlBytes(dataUrl) > IMAGE_MAX_BYTES) {
        alert('這張圖片壓縮後仍超過 200KB，請換一張較小 / 簡單的圖片。');
        return;
      }
      updateProduct(index, { image: dataUrl });
    } catch (err) {
      alert(err instanceof Error ? err.message : '圖片處理失敗，請換一張。');
    }
  }

  // 至少要有一個有效商品（名稱非空）才能開團。
  const validProducts = products.filter((p) => p.name.trim() !== '');
  const canSubmit = validProducts.length > 0;

  function handleSubmit() {
    if (!canSubmit) return;
    const payload: NewProduct[] = validProducts.map((p) => ({
      name: p.name,
      price: Number(p.price) || 0,
      ...(p.image ? { image: p.image } : {}),
    }));
    // datetime-local → epoch 毫秒（new Date 以主揪當地時區解讀，存絕對時間點）；
    // 空字串或解析失敗（NaN）→ 不設截止時間。
    const ts = deadline ? new Date(deadline).getTime() : NaN;
    const deadlineAt = Number.isFinite(ts) ? ts : undefined;

    // 防「開團即截止」：截止時間若已是過去（min 之外的手動輸入 / 貼上），先警示再決定。
    if (
      deadlineAt !== undefined &&
      deadlineAt <= Date.now() &&
      !confirm('截止時間已經是過去，這樣開團會立刻截止、無法收單。仍要繼續嗎？')
    ) {
      return;
    }

    // 寫入前概算 localStorage 總量：接近上限（>4MB）先警示，讓主揪決定是否繼續。
    const projected = estimateGroupsBytes([
      { name, note, deadlineAt, products: payload, orders: [] },
      ...groups,
    ]);
    if (
      projected > STORAGE_WARN_BYTES &&
      !confirm('本機儲存空間快滿了（多為商品圖片），繼續開團可能導致儲存失敗。仍要繼續嗎？')
    ) {
      return;
    }

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
          min={toLocalDatetimeInput(new Date())}
          onChange={(e) => setDeadline(e.target.value)}
        />
      </div>

      <div className="section-title">商品清單</div>
      {products.map((p, i) => (
        <div key={i} className="product-edit">
          <div className="line">
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
          <div className="line" style={{ marginBottom: 12 }}>
            {p.image && <img className="product-thumb" src={p.image} alt={`${p.name || '商品'} 圖片`} />}
            <label className="btn ghost-primary small" style={{ cursor: 'pointer' }}>
              {p.image ? '換圖片' : '＋ 圖片'}
              <input
                type="file"
                accept="image/*"
                style={{ display: 'none' }}
                onChange={(e) => {
                  handlePickImage(i, e.target.files?.[0]);
                  e.target.value = ''; // 允許重選同一檔
                }}
              />
            </label>
            {p.image && (
              <button
                className="btn danger small"
                onClick={() => updateProduct(i, { image: undefined })}
              >
                移除圖片
              </button>
            )}
          </div>
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
