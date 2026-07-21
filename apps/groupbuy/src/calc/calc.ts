// 團購金額統計純函式。
//
// 規則（MVP）：
//   單筆小計 = 商品單價 × 數量
//   一張訂單應付合計 = 該訂單所有品項小計加總
//   某商品累積數量 = 全部訂單裡該商品數量加總
//   某商品累積金額 = 累積數量 × 單價
//   全團總金額 = 各商品累積金額加總（= 各人應付合計加總，兩路必相等）
//
// 找不到對應商品的 OrderItem（例如商品已被主揪刪除）一律略過、不計入金額，
// 避免舊訂單殘留的品項污染統計。本檔不依賴 React / DOM，純資料進出。

import type { Group, Order, Product } from '../types';

/** 商品 id -> Product 的查表，供逐筆品項快速定價。 */
function indexProducts(products: Product[]): Map<string, Product> {
  const map = new Map<string, Product>();
  for (const p of products) map.set(p.id, p);
  return map;
}

/**
 * 一張訂單的應付合計。
 * 找不到商品（已被刪除）的品項略過不計。
 */
export function calcOrderSubtotal(order: Order, products: Product[]): number {
  const index = indexProducts(products);
  let total = 0;
  for (const item of order.items) {
    const product = index.get(item.productId);
    if (!product) continue;
    total += product.price * item.qty;
  }
  return total;
}

/** 單一商品的累積結果：總數量與總金額。 */
export interface ProductTotal {
  productId: string;
  name: string;
  price: number;
  qty: number;
  amount: number;
}

/**
 * 各商品的累積數量與金額。
 * 依 group.products 的順序回傳（含數量為 0 的商品，方便後台完整呈現品項）。
 */
export function calcProductTotals(group: Group): ProductTotal[] {
  const qtyByProduct = new Map<string, number>();
  for (const order of group.orders) {
    for (const item of order.items) {
      qtyByProduct.set(item.productId, (qtyByProduct.get(item.productId) ?? 0) + item.qty);
    }
  }
  return group.products.map((p) => {
    const qty = qtyByProduct.get(p.id) ?? 0;
    return {
      productId: p.id,
      name: p.name,
      price: p.price,
      qty,
      amount: qty * p.price,
    };
  });
}

/** 全團總金額（各商品累積金額加總）。 */
export function calcGroupTotal(group: Group): number {
  return calcProductTotals(group).reduce((sum, pt) => sum + pt.amount, 0);
}

/**
 * 未收款總金額：所有「尚未標記已收」訂單的應付合計加總。
 * order.paid 為 undefined（舊資料）或 false 都算未收款。
 */
export function calcUnpaidTotal(group: Group): number {
  return group.orders.reduce(
    (sum, o) => (o.paid ? sum : sum + calcOrderSubtotal(o, group.products)),
    0,
  );
}

/** 逐人明細裡的一個品項行。 */
export interface BuyerLine {
  productId: string;
  name: string;
  price: number;
  qty: number;
  subtotal: number;
}

/** 某位買家的完整明細：名字、各品項行、應付合計。 */
export interface BuyerBreakdown {
  buyerName: string;
  lines: BuyerLine[];
  total: number;
}

/**
 * 逐人明細：每位買家買了哪些品項、各小計與應付合計。
 * 只列出數量 > 0 的品項行；找不到商品的品項略過不計。
 * 依訂單原順序回傳（同名覆蓋後每人至多一張單，故等同買家順序）。
 */
export function calcBuyerBreakdowns(group: Group): BuyerBreakdown[] {
  const index = indexProducts(group.products);
  return group.orders.map((order) => {
    const lines: BuyerLine[] = [];
    let total = 0;
    for (const item of order.items) {
      const product = index.get(item.productId);
      if (!product || item.qty <= 0) continue;
      const subtotal = product.price * item.qty;
      total += subtotal;
      lines.push({
        productId: product.id,
        name: product.name,
        price: product.price,
        qty: item.qty,
        subtotal,
      });
    }
    return { buyerName: order.buyerName, lines, total };
  });
}
