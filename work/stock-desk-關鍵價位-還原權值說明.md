# 關鍵價位面板 — 各市場資料鏈還原權值狀態說明（R12 書面說明）

> 出具者：dev-lead（本 session 查證）
> 需求來源：risk-compliance-officer 2026-09-01 對「關鍵價位參考」面板之 VETO 第 R12 條。
> 用途：作為風控重審之前置文件；並據此在面板就近揭露「未還原權值」限制。

## 查證結論

**本產品目前所有行情資料鏈提供的都是未還原權值（unadjusted）的原始日線價格。**

| 市場 | 資料鏈 | 資料集 | 還原權值狀態 | 依據 |
|---|---|---|---|---|
| 台股上市 | TWSE | `exchangeReport/STOCK_DAY`（個股日成交資訊） | 未還原 | `backend/app/data/providers/twse.py:3-10`；STOCK_DAY 為原始成交價，TWSE 另有還原序列但本 build 未接 |
| 台股上市（備援） | FinMind | `TaiwanStockPrice` | 未還原 | `backend/app/data/providers/finmind.py:3-13`；FinMind 之還原序列為 `TaiwanStockPriceAdj`，本 build 未接 |
| 台股上櫃 | TPEx | 上櫃日成交資訊 | 未還原 | `backend/app/data/providers/tpex.py` |
| 美股 | Alpha Vantage | `TIME_SERIES_DAILY` | 未還原（刻意） | `backend/app/data/providers/alpha_vantage.py:9-14`：free tier 是否仍供應 `TIME_SERIES_DAILY_ADJUSTED` 屬「尚缺的事實」，本 build 刻意採未還原端點 |
| 離線示範 | demo_synthetic | 合成序列 | 不適用（無除權息事件） | `backend/app/demo/` |

## 對關鍵價位面板的影響

跨除權息日的所有回看視窗（區間高低、MA20／MA60、ATR(14)、近 60 日低點）
都會把除權息造成的價格跳空當成真實漲跌，導致位階與各參考水位失真；
除權息幅度越大、距今越近，失真越大。

## 處置

1. 面板須就近揭露「以未還原權值之原始收盤計算，跨除權息日之區間與均線可能失真」之意（字面由 creative-lead 成稿、風控逐字覆核）。
2. 中期改善（backlog，non-blocking）：台股接 FinMind `TaiwanStockPriceAdj`、美股查證 `TIME_SERIES_DAILY_ADJUSTED` 可用性後切換，屆時此揭露可撤——撤除需再過風控。
