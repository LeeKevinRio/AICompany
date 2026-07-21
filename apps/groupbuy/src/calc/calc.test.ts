import { describe, it, expect } from 'vitest';
import {
  calcBuyerBreakdowns,
  calcGroupTotal,
  calcOrderSubtotal,
  calcProductTotals,
  calcUnpaidTotal,
} from './calc';
import type { Group, Product } from '../types';

const products: Product[] = [
  { id: 'a', name: '雞排', price: 70 },
  { id: 'b', name: '珍奶', price: 50 },
  { id: 'c', name: '滷味', price: 100 },
];

function makeGroup(partial: Partial<Group>): Group {
  return {
    id: 'g1',
    name: '午餐團',
    products,
    orders: [],
    createdAt: 0,
    closed: false,
    ...partial,
  };
}

describe('calcOrderSubtotal', () => {
  it('單價 × 數量後加總各品項', () => {
    const order = {
      id: 'o1',
      buyerName: '小明',
      createdAt: 0,
      items: [
        { productId: 'a', qty: 2 }, // 70 × 2 = 140
        { productId: 'b', qty: 1 }, // 50 × 1 = 50
      ],
    };
    expect(calcOrderSubtotal(order, products)).toBe(190);
  });

  it('找不到的商品品項略過不計', () => {
    const order = {
      id: 'o2',
      buyerName: '小華',
      createdAt: 0,
      items: [
        { productId: 'a', qty: 1 }, // 70
        { productId: 'zzz', qty: 5 }, // 商品已刪除 → 0
      ],
    };
    expect(calcOrderSubtotal(order, products)).toBe(70);
  });

  it('空訂單合計為 0', () => {
    const order = { id: 'o3', buyerName: '空', createdAt: 0, items: [] };
    expect(calcOrderSubtotal(order, products)).toBe(0);
  });
});

describe('calcProductTotals', () => {
  it('跨訂單加總各商品數量與金額，並保留 0 數量商品', () => {
    const group = makeGroup({
      orders: [
        {
          id: 'o1',
          buyerName: '小明',
          createdAt: 0,
          items: [
            { productId: 'a', qty: 2 },
            { productId: 'b', qty: 1 },
          ],
        },
        {
          id: 'o2',
          buyerName: '小華',
          createdAt: 0,
          items: [{ productId: 'a', qty: 3 }],
        },
      ],
    });
    const totals = calcProductTotals(group);
    // 依 products 順序：a, b, c
    expect(totals.map((t) => t.qty)).toEqual([5, 1, 0]);
    expect(totals.map((t) => t.amount)).toEqual([350, 50, 0]); // 70×5, 50×1, 100×0
  });
});

describe('calcGroupTotal', () => {
  it('全團總金額 = 各商品金額加總', () => {
    const group = makeGroup({
      orders: [
        { id: 'o1', buyerName: '小明', createdAt: 0, items: [{ productId: 'a', qty: 2 }] },
        { id: 'o2', buyerName: '小華', createdAt: 0, items: [{ productId: 'c', qty: 1 }] },
      ],
    });
    expect(calcGroupTotal(group)).toBe(240); // 70×2 + 100×1
  });

  it('總金額 = 各人應付合計加總（兩路一致）', () => {
    const group = makeGroup({
      orders: [
        {
          id: 'o1',
          buyerName: '小明',
          createdAt: 0,
          items: [
            { productId: 'a', qty: 1 },
            { productId: 'b', qty: 2 },
          ],
        },
        {
          id: 'o2',
          buyerName: '小華',
          createdAt: 0,
          items: [{ productId: 'c', qty: 3 }],
        },
      ],
    });
    const byProduct = calcGroupTotal(group);
    const byBuyer = calcBuyerBreakdowns(group).reduce((s, b) => s + b.total, 0);
    expect(byProduct).toBe(byBuyer);
    expect(byProduct).toBe(470); // (70 + 100) + 300
  });
});

describe('calcBuyerBreakdowns', () => {
  it('逐人列出品項行與應付合計，略過 0 數量與已刪商品', () => {
    const group = makeGroup({
      orders: [
        {
          id: 'o1',
          buyerName: '小明',
          createdAt: 0,
          items: [
            { productId: 'a', qty: 2 }, // 140
            { productId: 'b', qty: 0 }, // 0 數量 → 不列
            { productId: 'gone', qty: 9 }, // 已刪 → 不列
          ],
        },
      ],
    });
    const [b] = calcBuyerBreakdowns(group);
    expect(b.buyerName).toBe('小明');
    expect(b.lines).toHaveLength(1);
    expect(b.lines[0]).toMatchObject({ name: '雞排', qty: 2, subtotal: 140 });
    expect(b.total).toBe(140);
  });
});

describe('calcUnpaidTotal', () => {
  it('未標記已收（含舊資料無 paid 欄位）全算未收款', () => {
    const group = makeGroup({
      orders: [
        { id: 'o1', buyerName: '小明', createdAt: 0, items: [{ productId: 'a', qty: 1 }] }, // 70，無 paid
        { id: 'o2', buyerName: '小華', createdAt: 0, items: [{ productId: 'b', qty: 2 }] }, // 100，無 paid
      ],
    });
    expect(calcUnpaidTotal(group)).toBe(170);
  });

  it('已收款訂單不計入未收款', () => {
    const group = makeGroup({
      orders: [
        { id: 'o1', buyerName: '小明', createdAt: 0, paid: true, items: [{ productId: 'a', qty: 1 }] }, // 70 已收
        { id: 'o2', buyerName: '小華', createdAt: 0, paid: false, items: [{ productId: 'c', qty: 1 }] }, // 100 未收
      ],
    });
    expect(calcUnpaidTotal(group)).toBe(100);
  });

  it('全部已收 → 0（結清）', () => {
    const group = makeGroup({
      orders: [
        { id: 'o1', buyerName: '小明', createdAt: 0, paid: true, items: [{ productId: 'a', qty: 1 }] },
      ],
    });
    expect(calcUnpaidTotal(group)).toBe(0);
  });
});
