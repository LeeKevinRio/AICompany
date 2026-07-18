// 回單碼編解碼（無後端的跨裝置回單機制）。
//
// 動線：買家從分享連結填完單 → 產生一段「回單碼」短文字 → 買家把回單碼貼回 LINE 給主揪 →
// 主揪在後台「貼上回單碼匯入」→ 訂單進入該團統計。買家裝置與主揪裝置各自獨立，靠這段
// 純文字搬運資料，不需後端。
//
// 格式：GBR1.<base64url(JSON)>.<crc>
//   - 前綴 GBR1 便於從 LINE 訊息雜訊中用 regex 抓出來（買家常會連同其他字一起貼）。
//   - crc 是 payload 的短檢查碼，用來偵測貼歪 / 被截斷的壞碼（不符即判無效）。
//   - payload 短鍵 JSON：{ v:1, g:groupId, b:buyerName, o?:note, it:[[productId,qty],...] }
//
// 容錯要「特別厚」：任何解不開 / crc 不符 / 缺欄位一律回 null，絕不丟例外。

import type { OrderItem } from '../types';
import { decodeBase64Url, encodeBase64Url } from './base64url';

const PREFIX = 'GBR1';
const SCHEMA_VERSION = 1;

/** 從回單碼還原的訂單（供主揪後台匯入）。 */
export interface ParsedReceipt {
  groupId: string;
  buyerName: string;
  items: OrderItem[];
  note?: string;
}

/** 編碼來源：一張買家訂單的必要資訊。 */
export interface ReceiptSource {
  groupId: string;
  buyerName: string;
  items: OrderItem[];
  note?: string;
}

function isNonNegInt(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v) && Number.isInteger(v) && v >= 0;
}

/** 對 payload 算一個短檢查碼（djb2 變體 → base36），用於偵測截斷 / 貼歪。 */
function checksum(payload: string): string {
  let h = 5381;
  for (let i = 0; i < payload.length; i += 1) {
    h = ((h << 5) + h + payload.charCodeAt(i)) >>> 0; // 保持 32-bit 無號
  }
  return h.toString(36);
}

/** 買家訂單 → 回單碼字串。 */
export function encodeReceipt(source: ReceiptSource): string {
  const obj = {
    v: SCHEMA_VERSION,
    g: source.groupId,
    b: source.buyerName,
    ...(source.note ? { o: source.note } : {}),
    it: source.items.filter((i) => i.qty > 0).map((i) => [i.productId, i.qty]),
  };
  const payload = encodeBase64Url(JSON.stringify(obj));
  return `${PREFIX}.${payload}.${checksum(payload)}`;
}

/**
 * 從一段可能夾雜其他文字的訊息裡，抓出第一個回單碼並解碼。
 * 抓不到 / crc 不符 / 壞碼一律回 null，不丟例外。
 */
export function decodeReceipt(text: string): ParsedReceipt | null {
  if (typeof text !== 'string' || text.length === 0) return null;

  // 從雜訊中擷取 GBR1.<payload>.<crc>（payload 為 base64url，crc 為 base36）。
  const match = text.match(/GBR1\.([A-Za-z0-9_-]+)\.([a-z0-9]+)/);
  if (!match) return null;
  const [, payload, crc] = match;

  // crc 檢查：偵測截斷 / 貼歪。
  if (checksum(payload) !== crc) return null;

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

  if (d.v !== SCHEMA_VERSION) return null;
  if (typeof d.g !== 'string' || d.g.length === 0) return null;
  if (typeof d.b !== 'string' || d.b.trim().length === 0) return null;
  if (!Array.isArray(d.it)) return null;

  const items: OrderItem[] = [];
  for (const entry of d.it) {
    if (!Array.isArray(entry) || entry.length < 2) continue;
    const [productId, qty] = entry;
    if (typeof productId !== 'string' || productId.length === 0) continue;
    if (!isNonNegInt(qty) || qty <= 0) continue;
    items.push({ productId, qty });
  }

  return {
    groupId: d.g,
    buyerName: d.b.trim(),
    ...(typeof d.o === 'string' && d.o.length > 0 ? { note: d.o } : {}),
    items,
  };
}
