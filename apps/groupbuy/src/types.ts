// 核心資料型別：團（Group）/ 商品（Product）/ 訂單（Order）
// 這層完全不依賴 React 或 DOM，未來可被原生 app 直接重用。

/** 商品：一個團購活動裡的品項，名稱 + 單價 */
export interface Product {
  id: string;
  name: string;
  price: number; // 單價（非負整數，單位：元）
}

/** 一張訂單裡的一個品項：買哪個商品、買幾個 */
export interface OrderItem {
  productId: string;
  qty: number; // 數量（非負整數）
}

/**
 * 一張訂單：某人一次填單的內容。
 * MVP 定案：同名覆蓋——同一團內以 buyerName 為識別，
 * 再次以相同名字送出會覆蓋原本那張訂單（等同「修改我的單」）。
 */
export interface Order {
  id: string;
  buyerName: string;
  items: OrderItem[];
  createdAt: number;
  /**
   * 主揪是否已向此人收到款。
   * optional：舊資料無此欄位 → undefined，視為「未收款」（中性、不影響歷史）。
   */
  paid?: boolean;
}

/** 一個團購活動（主揪開的一張表單） */
export interface Group {
  id: string;
  name: string; // 團名
  note?: string; // 截止註記 / 備註（可選，例：7/20 晚上 8 點截止）
  products: Product[];
  orders: Order[];
  createdAt: number;
  /** 是否已截止（主揪手動切換）。截止後填單頁不再接受新單。 */
  closed: boolean;
}

/** 商品名稱長度上限 */
export const MAX_PRODUCT_NAME_LENGTH = 30;

/** 團名長度上限 */
export const MAX_GROUP_NAME_LENGTH = 40;

/** 買家名字長度上限 */
export const MAX_BUYER_NAME_LENGTH = 20;

/** 單一品項數量上限（防呆，避免誤植天量） */
export const MAX_ITEM_QTY = 999;
