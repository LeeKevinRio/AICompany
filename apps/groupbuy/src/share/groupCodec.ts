// 團定義的分享編解碼（無後端）：把團名 / 商品 / 價格 / 截止註記壓進 URL。
//
// 設計（方案 C）：買家永遠從主揪分享的連結進填單頁，不進 app 首頁。買家裝置本機沒有這個團，
// 因此團定義必須「整包」帶在 URL 裡（而非只帶 group id），才能跨裝置在買家瀏覽器還原填單頁。
//
// 格式：{base}#/join?d=<base64url(JSON)>，hash route 免伺服器 rewrite、硬重整不 404。
// payload 用短鍵壓縮，降低 URL / QR 長度：
//   { v:1, i:groupId, n:name, o?:note, p:[[id,name,price], ...] }
//
// decode 容錯要厚：任何欄位缺 / 型別錯 / 非 JSON / 壞 base64 一律回傳 null 或濾掉壞項，不丟例外。

import type { Product } from '../types';
import { decodeBase64Url, encodeBase64Url } from './base64url';

/** 分享連結還原出的團定義（買家填單頁用；不含訂單、不含收款狀態）。 */
export interface SharedGroupDef {
  groupId: string;
  name: string;
  note?: string;
  /** 自動截止時間（epoch 毫秒，可選）；買家端據此擋過期填單（以買家裝置時鐘為準）。 */
  deadlineAt?: number;
  products: Product[];
}

const SCHEMA_VERSION = 1;

/** 供 encode 的最小來源形狀（相容 Group，也可只傳必要欄位）。 */
export interface ShareableGroup {
  id: string;
  name: string;
  note?: string;
  deadlineAt?: number;
  products: Product[];
}

function isNonNegInt(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v) && Number.isInteger(v) && v >= 0;
}

/** 團定義 → base64url payload（放進 URL 的 d 參數值）。 */
export function encodeGroupPayload(group: ShareableGroup): string {
  const payload = {
    v: SCHEMA_VERSION,
    i: group.id,
    n: group.name,
    ...(group.note ? { o: group.note } : {}),
    // 截止時間（dl）很小，直接放進 URL；舊連結無此欄位，decode 相容。
    ...(typeof group.deadlineAt === 'number' && Number.isFinite(group.deadlineAt)
      ? { dl: group.deadlineAt }
      : {}),
    p: group.products.map((p) => [p.id, p.name, p.price]),
  };
  return encodeBase64Url(JSON.stringify(payload));
}

/**
 * base64url payload → 團定義。壞碼 / 缺欄位 → null；個別壞掉的商品項濾掉而非整包丟棄。
 */
export function decodeGroupPayload(payload: string): SharedGroupDef | null {
  const json = decodeBase64Url(payload);
  if (json === null) return null;

  let data: unknown;
  try {
    data = JSON.parse(json);
  } catch {
    return null;
  }
  if (typeof data !== 'object' || data === null) return null;
  const d = data as Record<string, unknown>;

  // 版本不符先擋（未來格式演進時避免誤解舊 / 新碼）。
  if (d.v !== SCHEMA_VERSION) return null;
  if (typeof d.i !== 'string' || d.i.length === 0) return null;
  if (typeof d.n !== 'string') return null;
  if (!Array.isArray(d.p)) return null;

  const products: Product[] = [];
  const seenIds = new Set<string>();
  for (const item of d.p) {
    if (!Array.isArray(item) || item.length < 3) continue;
    const [id, name, price] = item;
    if (typeof id !== 'string' || id.length === 0 || seenIds.has(id)) continue;
    if (typeof name !== 'string') continue;
    if (!isNonNegInt(price)) continue;
    seenIds.add(id);
    products.push({ id, name, price });
  }

  return {
    groupId: d.i,
    name: d.n,
    ...(typeof d.o === 'string' && d.o.length > 0 ? { note: d.o } : {}),
    // dl 缺（舊連結）或非法 → 不帶 deadlineAt（＝買家端不擋過期）。
    ...(typeof d.dl === 'number' && Number.isFinite(d.dl) ? { deadlineAt: d.dl } : {}),
    products,
  };
}

/** 組出完整分享連結。base 例：`https://host/path/`（呼叫端帶入 location.origin+pathname）。 */
export function buildShareUrl(group: ShareableGroup, base: string): string {
  const payload = encodeGroupPayload(group);
  // 確保 base 與 hash 之間只有一個 '#'；base 可含或不含結尾斜線。
  const clean = base.replace(/#.*$/, '');
  return `${clean}#/join?d=${payload}`;
}

/**
 * 從 hash 字串（如 `#/join?d=XXXX` 或完整 URL）取出 d 參數並解碼成團定義。
 * 取不到 / 解不開一律回傳 null。
 */
export function parseShareTarget(hashOrUrl: string): SharedGroupDef | null {
  if (typeof hashOrUrl !== 'string') return null;
  const qIndex = hashOrUrl.indexOf('?');
  if (qIndex < 0) return null;
  const query = hashOrUrl.slice(qIndex + 1);
  let d: string | null = null;
  try {
    d = new URLSearchParams(query).get('d');
  } catch {
    return null;
  }
  if (!d) return null;
  return decodeGroupPayload(d);
}
