# 審查紀錄:RISK-FIX 六條必修的 code review

- 審查者:qa-reviewer
- 日期:2026-08-08
- 範圍:product/stock-desk,`git diff 702c422..c02cb28`(R1–R6 六個 fix commit)
- Codex 第二意見:不可用(codex CLI 未安裝、OPENAI_API_KEY 未設),依降級策略改強化人工複查

## BLOCKING_ISSUES

- B1 `lib/tradingCalendar.ts`(high):`isTradingDay` 只排除週末與 2 個固定假日(元旦、聖誕節,
  後者甚至非 TWSE 休市日),農曆春節等真實休市日全被當成交易日計入 gap——封關後恢復交易首日,
  最新資料會被誤判 `tradingDaysSince > 1` 而觸發「資料過舊」顯著警示。這是 R4 明令消除的
  誤報類別換路徑重生,且每年必發。檔案註解自稱 under-count(false negative、方向保守)
  與實際 over-count(false positive)完全相反。8 個新測試只測已建模假日,
  「未建模長假恢復交易不誤報」場景零覆蓋。
  修正方向:未建模休市日不得反向膨脹計數(找不到明確行事曆時寧可不計入),或改用 as-of
  資料源的交易行事曆;補「長假恢復首日不誤報」測試釘住。

## 非阻擋建議(列管)

- N1 `tradingDaysSince` 用 UTC 日曆日,台北 UTC+8 跨日區間計數偏低(方向恰好安全但屬巧合),文件與測試皆未提及
- N2 措辭掃描為逐字比對,RiskGauge「勝率」改寫可接受,但掃描不分「禁止語境/承認缺失語境」日後恐再誤殺
- N3 `insufficient_data` 分支不帶 staleDataNotice(既有行為非本次回歸),另開票追蹤

## 通過項目

R1 標籤同定調原文;R2 確認真同源(`buildAttributedHeadline` 單一來源,CARD_ACTION_LABELS 全庫無殘留);
R3 與 DisclaimerBanner 樣式逐 class 一致、無重複渲染;R4 的 cached_stale 徽章路徑獨立無空窗;
R5 五檔掃描無違禁詞;R6 限定語齊。11 項新測試皆斷言公開行為。

結論:NEEDS_CHANGES(僅 B1;複審只需看 R4 變更範圍)
