# 審查紀錄:RISK-FINAL 股票措辭定稿風控複審

- 審查者:risk-compliance-officer
- 日期:2026-08-08
- 審查範圍:product/stock-desk @ 58b204f,面向使用者的建議措辭全數(派工單 2026-08-08-risk-final.md)
- Codex 第二意見:不適用(風控閘門,非 code review)

## 發現事項(required,未改完不得上線)

- R1 `format.ts:193`:`insufficient_data` 標籤寫成「資訊不足,不建議」——把「無法評估」
  輸出成引擎未曾產生的方向性判斷。改回定調 §1.2 原文「資料不足,本次不提供操作評估」。
- R2 `format.ts:187-194` + `AdviceCardView.tsx:27-33`:建議卡動作徽章為無主詞裸動詞
  (「加碼」「減碼」⋯),違反 §1.1 歸屬語與 §1.2 名詞化白名單;且與上方摘要的
  「規則評估:加碼參考」同頁矛盾。改用 adviceWording.ts 的標籤來源,刪除第二套標籤。
- R3 `AdviceCardView.tsx:163-165`:免責聲明字級最小、色階最暗、隔線置底,違反 §2.1
  三項限制。比照 OperationSummaryPanel 的 DisclaimerBanner 處理。
- R4 `operationSummary.ts:165`:資料過舊顯著提示誤綁 `cached_stale`(來源降級狀態),
  非資料年齡——會產生同畫面矛盾陳述(誤報)且長假/停牌時漏報。改以 `last_bar_date`
  與當下的交易日差計算;來源降級另行以徽章表達。
- R5 `componentWordingScan.test.ts:27-36`:措辭掃描未涵蓋 AdviceCardView.tsx、format.ts、
  RiskGauge.tsx、LimitsCheckList.tsx、operationSummary.ts。補入(防回歸;不取代 R1/R2 人工修正)。
- R6 `SettingsForm.tsx:48,61,86`、`RiskGauge.tsx:38`:「總資產」未附定調 §a 連動裁定的
  限定語「總資產(已估值部位市值)」,與設定頁的「帳戶總淨值」分母混淆。

## 發現事項(suggested,列管不擋)

S1 前端時間戳未標「(台北時間)」/ S2 not_evaluable 仍畫空進度條 / S3 context_notes 預設收合 /
S4 放寬確認僅涵蓋總曝險 / S5 as-of 語句可能退化為破折號空句 / S6 禁用詞清單前後端鏡像會漂移 /
S7 美股選項無 adapter 卻可選。

## 通過部分(下次僅需複審 R1–R6 涉及檔案)

adviceWording.ts 措辭本體、八項必附元素契約測試、候選模式五項保守度全數、FR-9 揭露三句與
淨值時間在地化(單獨 APPROVE)、§b/§c/§f、已知限制未被畫面掩蓋、全檔無保證性字眼。
§4 停損參考位未觸發,紅線乾淨。

結論:VETO

---

## 複審(2026-08-09,R1–R6 修復後)

- R1–R5:全數符合(標籤同源、歸屬語寫死在函式體、免責聲明逐 class 一致、掃描補齊)。
- R4 保守策略(日曆日差 >10)裁定**接受**:as-of 時間戳無條件常駐,漏報的只是加重提示層;
  誤報(春節後必發假警示)侵蝕警示信任,成本更高。列管:後端一旦提供交易行事曆,
  須改回真實交易日差、門檻降回 1 交易日,屆時重審。
- R6 **不符合**:V1 `SettingsForm.tsx:61` 第 3 條分母講錯(後端 limits.py 明寫 FR-9 option B
  分母為自報淨值,與同頁 NetWorthSection/RiskGauge 矛盾)——上次行號是我指錯,書面認錯,
  但錯誤文案仍不得上線;V2 `:68` 第 4 條仍裸「總資產」漏限定語。
- 文案裁決:STALE_DATA_PROMINENT_NOTICE **必須改**(裁決 b)。理由:讀者會反推「落後五天
  會講更嚴重」,但系統 1–10 日間不出聲,量級被藏。核可措辭 A(優先):
  「本評估所依據的收盤資料為 {lastBarDate},距今已 {days} 個日曆日未更新,僅供參考,
  不代表最新市況。」B 案:門檻數字須由常數插值不得寫死。並修 adviceWording.ts:116 過期註解。
- 「勝率→歷史交易的獲勝比例」:可接受(承認能力缺口語境)。列管:backend limits.py:645,653
  仍含「勝率」,win_rate 資料源接入前該兩句須先送審。
- suggested:SettingsForm.tsx:55 第 2 條裸「總資產」建議補齊(恆 not_evaluable,不擋)。

結論:**VETO**(V1/V2/V3 三條必修;複審僅看 SettingsForm.tsx 與 adviceWording.ts 兩檔)

---

## 最終複審(2026-08-09):APPROVE

- V1/V2/V3 逐條符合核可措辭並與後端計算逐項對應,順手項無害。否決理由:無。
- 風控官聲明:全部面向使用者的建議類措辭已符合定調,產品風控關放行。
- 新列管(下批文案清理):adviceWording.ts:124 半形逗號統一、:95 CANDIDATE_QUANTITY_BASIS_NOTE
  裸「總資產」補限定語、SettingsForm.tsx:42「加碼建議/加碼參考」用詞對齊。
- 沿用列管:門檻 10 日俟後端行事曆改真實交易日差重審;limits.py:645,653「勝率」接資料源前送審。
