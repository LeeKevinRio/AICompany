# 派工單:市調首發——stock-desk 數據核實與雙產品合理性市調

- **狀態**:done
- **承辦**:market-researcher
- **委託人**:CEO
- **日期**:2026-08-09
- **產出**:
  - `work/research/2026-08-09-stock-desk數據核實.md`
  - `work/research/2026-08-09-產品合理性市調.md`

## 結果摘要

### 一、stock-desk 數據核實
- **本機無任何真實市場資料可抽**:`stock-desk.db` 為空;`ceo-test.db` 1,560 筆日線全為 `source='demo_synthetic'` 合成資料(標記機制健全)。fixtures 亦全為手工合成。
- 逐筆比對無法執行(0 筆可核);且本環境 WebFetch 對 TWSE/Yahoo 等財經網域被 egress 擋下,無法取得權威逐日行情,依紅線不引用二手摘要數字充當比對基準。
- 改走替代路線:六個 adapter 的來源可信度核實(TWSE 官方最高;**TPEx 用的是 legacy 端點,存廢未知,列 P0 驗證**;FinMind 600 次/時免費備援;yfinance 走無官方文件端點最弱),並產出 10 項上線前數據核實 checklist。
- 已知資料缺口致命性:資料源從未經真實環境驗證=上線前致命(可用 checklist 一次解除);無除權息還原=重要不致命但商業化前必解。
- 附帶發現:限制文件第 1、2 項已過時(Phase 7 已實作 US/指數 adapter),需 tech-writer 更新。

### 二、產品合理性市調
- **stock-desk verdict:可做,但要改**。看盤/行情是免費紅海;唯一空位是「持倉後規則式紀律管理」。最大障礙是法規初篩紅旗:建議卡(add/reduce)一旦收費,高度可能落入證投顧法投顧業務(第 107 條刑責),**待 risk-compliance-officer 確認**;商業化建議去建議化或維持自用/開源。
- **團購 app verdict:不建議**(repo 內無任何既有規劃,已註記)。市場規模上看千億但消費者端被 LINE/蝦皮佔滿,團媽工具端已有飛比+1、好賣+、樂賣等現役玩家;營運重、信任驅動,與一人+AI 產能結構錯配。若要進場,前置條件為 5–10 位團媽訪談取得付費痛點。

## 交接
- 法規疑慮 → risk-compliance-officer(函釋原文待調)。
- 數據核實 checklist → data-engineer;文件更新 → tech-writer。
- 兩份報告定稿 → CEO。
