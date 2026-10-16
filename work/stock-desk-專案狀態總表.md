# Stock Desk 專案狀態總表（初版）

- 日期：2026-10-16
- 維護：product-manager（任務 T1-04；對應新 PRD NP-G2、P0-8）
- 狀態：**初版，draft**。不經 coordinator 核對前，不得當作對 CEO 的正式狀態宣稱。
- 對應文件：`work/stock-desk-新定位-PRD-2026-10-16.md`（下稱「新 PRD」，commit 1adf158）

## 0. 狀態詞定義與讀法

| 狀態 | 定義 |
|---|---|
| 已完成 | 有 commit（或 accepted 的文件）與審查紀錄，且已合併或已定案 |
| 待合併 | 實作與審查（含實機驗收）已通過，但**合併條件未滿足**；不得標 done（章程 §2：通過審查才算完成） |
| 規劃中 | 只有文件或尚未開工，沒有可交付的程式 |
| 受阻 | 有明列的前置條件未解（寫明卡在誰的決定或什麼資源） |
| 未核實 | PM 只讀到過時的狀態行，**沒有核對最新狀態**；不歸入以上任何一類，也不得被當成已完成 |

讀法限制：
- 任務單的「狀態」行常落後於內文更新（例：KT-1 任務單 L3 仍寫 draft，L30 才是 review／risk-gate）。本表以**最新段落**為準，並標出依據。
- 「依據」欄的路徑都是我在本次或先前工作中讀到的檔案；沒有重新執行任何測試，也沒有核對 git 合併狀態，合併與否一律引自 coordinator 決策包與任務單。
- **Codex 缺席是跨項目的系統性問題**：章程 §3 要求每個 PR 含 Codex 第二意見，現環境不可用（`codex` exit 127）。凡標「單家審查」的已合併項目，追溯處理（補跑或 CEO 書面接受）仍待 CEO 決定（決策包第四節-a）。

---

## 1. 已完成

| 項目 | 狀態說明 | 依據 |
|---|---|---|
| ADR-0025 產品定位改為提供投資建議 | accepted，CEO 2026-10-16 書面核可（含 ADR-0004 部分修訂、ADR-0012 C-15 部分修訂、知悉 ADR-0018 被取代） | `docs/adr/0025-stock-desk-產品定位改為提供投資建議.md` 第 3 行；`work/dispatch/2026-10-16-CEO決策-ADR-0025核可與五日方向.md` |
| ADR-0004、ADR-0012 修訂指標；ADR-0018 superseded | ADR-0018 檔頭已確認為 `superseded by ADR-0025`；ADR-0004、ADR-0012 檔頭修訂指標依 tech-writer 回報已加，**PM 未逐檔核對** | `work/reviews/2026-10-16-ADR-0025核可落檔-tech-writer.md`；`docs/adr/0018-…` 第 3 行 |
| ADR-0024 日線價格幣別閘門與代號准入 | accepted，CEO 2026-10-14 | `docs/adr/0024-stock-desk-日線價格幣別閘門與代號准入.md` 第 3 行；`work/dispatch/2026-10-08-任務單-F-9-日線上游幣別未核對.md` L121 |
| 風控新護欄 PV-1～PV-52 | 已出具；依其自述於 ADR-0025 核可後生效（生效範圍為 coordinator 定案，CEO 可推翻） | `work/reviews/2026-10-15-新定位風控護欄重訂-PV1至PV52-風控.md`；CEO 決策紀錄「生效範圍」 |
| 風控對 A-15 事先宣告草案的裁定（R-1～R-8、PA-1～PA-11） | 已出具 2026-10-16（針對草案，**不等於草案已凍結**） | `work/reviews/2026-10-16-A-15-事先宣告草案R-1至R-8與PA-1至PA-11-風控.md` |
| F-9b 日線幣別閘門 | 已合併（引自決策包）；單家審查（Codex 未跑） | `work/dispatch/2026-10-15-決策包-ADR-0025與新定位.md` 第四節；`work/reviews/2026-10-13-F-9b-收尾審查-qa-reviewer.md`、`...-實機驗收-qa-e2e判讀.md` |
| F-11 回測報告補逐筆往返與樣本標示 | 已合併（引自決策包）；單家審查 | 決策包第四節；`work/reviews/2026-10-13-F-11-實機驗收-qa-e2e判讀-G1至G8.md` |
| F11-W38、F-6 殘項 | 已合併（引自決策包）；單家審查 | 決策包第四節；`work/reviews/2026-10-13-F11-W38修正審查-qa-reviewer.md`、`...F-6殘餘補件審查-qa-reviewer.md` |
| KT-R-22（尾段未歸屬評估） | 結案；`sector_eval` 無尾段問題。**其待辦 KT-R-31／32／34 不屬已完成**，見 §5 | `work/reviews/2026-10-14-KT-R-22結案裁示-風控-KT-R29至R35.md` |
| PR-0 決策卡第 4 條 ATR 回填繞過 book 層撤下 | done，commit 9f5166e，已 push 至 `product/stock-desk` | `work/dispatch/2026-10-07-任務單-PR-0-決策卡第4條ATR回填繞過book層撤下.md` L402 |
| 6-a PR-1（決策卡第 1、5 條未估值批次） | PR-1 done，commit be64f49，已 push；**6-a 的 PR-2、6-b 不在此列** | `work/dispatch/2026-10-07-任務單-6-a-決策卡第1與第5條在本標的有未估值批次時偏低.md` L225 |
| risk_limit 全部 not_evaluable 時 skipped 句尾只接匯率失敗成因 | done（審查通過） | `work/dispatch/2026-10-07-任務單-risk_limit全部not_evaluable時skipped句尾只接匯率失敗成因.md` L60 |
| 槓桿章節「實際報酬」「小節標題」改字 | done，commit 1dd9515、b4dc059；Codex 未執行 | `work/dispatch/2026-10-03-槓桿章節-實際報酬-改字.md`、`...-小節標題-改字.md` |

---

## 2. 待合併

三項皆已通過 qa-reviewer 與（涉及 UI 者）qa-e2e，**卡點相同：Codex 缺席，待 CEO 決定**——(a) 想辦法實際跑 Codex，或 (b) CEO 書面接受單家審查（含綁定 HEAD、Codex 不可用原因、日後補跑承諾）。

| 項目 | 狀態說明 | 卡點 | 依據 |
|---|---|---|---|
| A-1 全缺價總額顯示「—」（前端） | commit 27dc826。qa-reviewer PASS、BLOCKING_ISSUES=false；qa-e2e PASS（以 e2e-fallback 由 qa-automation 代跑）。**只完成前端**；後端 `Totals` 仍為非空 Decimal，後端另列 NP-B4b（規劃中，見 §3） | Codex 缺席待 CEO 決定 | `work/reviews/2026-10-15-A-1-全缺價總額顯示-qa-reviewer.md`、`...-e2e代跑證據包-qa-automation.md`、`...-e2e驗收-qa-e2e.md` |
| F-9b2 日線幣別閘門 attempt log（rejection 欄位）與 layer 0 前置守門 | qa-reviewer 程式審查與收尾 delta 審查 PASS（附條件：合併前補 Codex 或 CEO 明示放行）；tech-architect R-81～R-87 疑點確認、風控 F9W-53～57 字面落地確認均已出具 | Codex 缺席待 CEO 決定 | `work/reviews/2026-10-14-F-9b2-程式審查-qa-reviewer.md`、`...-收尾delta審查-qa-reviewer.md`、`...-tech-architect-F-9b2疑點確認R-81至R-87.md`、`...-F-9b2-字面落地與2e交互-F9W-53至F9W-57-風控.md` |
| KT-1 Kelly 未平倉／跨界字面修正與回測迄日顯示 | 分支 `feat/stock-desk-kt1`，出貨 HEAD 候選 e505845；qa-reviewer PASS、delta 審查 PASS（KT-R-27-1）、測試實跑原始輸出已留存（KT-R-27-2）、qa-e2e PASS、風控字面落地確認 APPROVE WITH CONDITIONS（KT-R-23～28）。任務單狀態為 review／risk-gate，不得標 done | Codex 缺席待 CEO 決定（KT-R-26），另需 CEO 排定時程 | `work/dispatch/2026-10-13-任務單-KT-1-Kelly未平倉跨界字面修正.md` L21-L32；`work/reviews/2026-10-13-KT-1-*` |

---

## 3. 規劃中

### 3.1 文件與治理（新 PRD Phase 0）

| 項目 | 狀態說明 | 依據／對應 |
|---|---|---|
| 新定位 PRD | draft v1 已提交（1adf158，coordinator 告知）；**未經 tech-architect 技術評估**，Phase 3～5 的 AC 較粗 | 新 PRD；`work/reviews/2026-10-16-新定位PRD-PM回報.md` |
| quant 事先宣告草案（`dirdef-v1.0`） | draft，**未凍結**（受阻於 #18～#22，見 §4）；需依風控 A-15 裁定修訂，並與 ADR D-6 調和（PA-1） | `work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md` |
| creative-lead 字面遷移清單（P0-4） | 未開工；全站舊定位句分散於 15 個檔案，須與功能同批出貨 | 新 PRD P0-4、NP-0；風控 PV 第（三）節 |
| art-lead 視覺規範（P0-5） | 未開工 | 新 PRD P0-5 |
| ADR-0026 庫存版本化與還原點（P0-7） | CEO 核可立案；待 tech-architect 起草 | CEO 決策紀錄 #8；新 PRD §6 T1-06 |
| 專案狀態總表（P0-8、T1-04） | 本文件初版 | 本文件 |
| 庫存頁 PRD 範圍外聲明加註（T1-05） | 已加註（原文保留），待 coordinator 轉知下游 | `work/stock-desk-庫存頁-PRD.md` 文末變更紀錄 2026-10-16 |

### 3.2 功能（依新 PRD 期別；全部尚無程式）

| 期別 | 項目 | 備註 |
|---|---|---|
| Phase 1 | NP-B4b 後端 `Totals` 在 `no_data` 時為 null | 先由 tech-architect 評估影響面（T1-01） |
| Phase 1 | NP-B5a 估值狀態標籤；NP-B5b 官方休市日 | 字面須風控逐字審；休市日查證卡 #15 |
| Phase 1 | NP-V2a 公司行動偵測；NP-V2b 官方指數來源；NP-E2a 費率查證 | 查證類卡 #15，見 §4 |
| Phase 1 | NP-E1a 持有時停損錨點改為最新收盤（**候選，待 CEO R-6**） | 風控 R-6（high）；最晚期限＝新定位聲明上線 |
| Phase 2 | NP-B2 軟刪除與修改歷史；NP-B3a 匯出；NP-B3b CSV 匯入預覽、重複偵測、合併、取代；NP-B3c 還原點；NP-B7a／b schema 版本、遷移前備份、DB 路徑守門；NP-B6 對外送出資料說明 | 需 ADR-0026。**CSV 去重不提前**（coordinator 2026-10-16 定案，CEO 可推翻）；NP-E2b 見 §4 |
| Phase 3 | `app/forecast`、`app/keylevels`、`app/outlook`、`app/plan`、taxonomy 主層、歷史回放報告、自選股清單 | 不出貨使用者面顯示；quant 凍結見 §4 |
| Phase 4 | 市場總覽天氣與展望、族群列表與詳細頁、個股行動計畫卡、狀態元件、視覺改版 | 顯示受 #10 與風控分層約束，見 §4 |
| Phase 5 | 基本面、官方重大訊息、組合相關性、交易日誌、校準機率（另立 ADR） | 較粗，進入時各自展開 |

細節與驗收條件見新 PRD §5；派工見新 PRD §6。

---

## 4. 受阻

| 項目 | 卡點（誰的決定／什麼資源） | 依據 |
|---|---|---|
| F-9c yfinance `meta.currency` 誠實回報 | F-9b2 須先合併；真實 fixture 與連網實證（#15 連網環境）；任務單六項硬性前提 | F-9 任務單；新 PRD T1-11、T1-21 |
| 官方休市日、官方指數、公司行動、費率的查證（T1-07～T1-10） | #15：需能連網的環境（CEO 本機代跑或另設）；本環境無法連外 | 決策包 #15；新 PRD §6.2 |
| quant 凍結 `dirdef-v1.0`；任何歷史回放執行 | #18～#22（CEO 回覆）；另需 tech-architect／quant 調和 ADR D-6 差異（風控 PA-1） | 決策包「三之一」；風控 A-15 裁定 PA-1 |
| NP-E2b 可用現金自報欄位；`add_conditional` 的預算條件 | #13。不加欄位的後果：預算條件恆為 `unavailable`，系統不會輸出「符合條件後可加碼」 | 決策包 #13；ADR D-4.4；新 PRD §0 第 5 點 |
| Phase 4 所有使用者面的展望顯示 | #10 顯示閘門（風控建議 (a) 加 Phase 3 上線紀錄 N ≥ 10 且各 horizon 至少 1 筆完成結算；為建議，非決定）。族群 150 閘門與個股只放詳細頁由風控裁定，不隨 #10 改變 | 決策包 #10；風控 A-15 裁定 R-5、PA-9 |
| 族群展望的資料輸入、族群列表 | 族群 board 能否產出榜單：`.env` 修法與族群卡本機檢查結果仍待 CEO（決策包第四節） | 決策包第四節；新 PRD §4 第四節-b |
| 細項與題材（金融、營建、醫療） | #14（由誰整理） | 決策包 #14 |
| 推播是否帶建議內容 | #16；PV-51 現行條文＝未經 CEO 同意不帶 | 決策包 #16 |
| 盤中價（估值狀態的盤中部分） | ADR-0014 仍 proposed；盤中價路線（TradingView 或 ADR-0014）待 CEO。**不在 ADR-0025 D-12 任何一期** | `docs/adr/0014-…` 第 3 行；決策包第四節 |
| NP-E1a 持有時停損錨點小修 | CEO 裁示 R-6：Phase 1 小修或書面延到 Phase 4 | 風控 A-15 裁定 R-6 |
| 設定頁對外送出資料說明的形式；還原點保留數；基本面先於消息面；視覺 token 先做；警示略過原因立案 | #17 各子項 | 決策包 #17；新 PRD §4 |

---

## 5. 未核實（PM 只讀到過時狀態行，歸類待 coordinator 補核）

這些項目**不得被當成已完成或已受阻**。「狀態行所載」是我讀到的字面，不代表現況。

| 項目 | 狀態行所載 | 來源 |
|---|---|---|
| F-1b 匯率非正值的估值防護 | 舊總綱 §3.1 稱 spec → build-ready，開工待 CEO 排序（PM 引自任務單，本次未重讀） | 舊總綱 §3.1 |
| O-1 API 行程 logging 設定 | 舊總綱稱 draft | 舊總綱 §3.1；`work/dispatch/2026-10-07-任務單-O-1-API行程logging設定.md` |
| RK-2 發布；RK-4、RK-5 | RK-4：spec（待風控依 2026-09-19 標準重新裁定）；RK-5：spec（待風控裁定與 CEO 排序）；RK-2 未讀 | `work/dispatch/2026-10-08-任務單-RK-4-…`、`...-RK-5-…`、`...-RK-2-…` |
| F-6 首次取價失敗快取缺 reason | 檔內有兩個狀態段：L33 draft → 待 CEO 立案；L40 build（程式面完成）→ 待補件後 done。決策包稱「F-6 殘項已合併」，已列 §1，但 F-6 本體的 (4) 併下一輪 e2e 未核實 | `work/dispatch/2026-10-08-任務單-F-6-…` |
| 產業上限對同產業未估值持股的判定與揭露 | review → e2e 待驗（合併前提：e2e 第二十五輪 RM-5 通過） | `work/dispatch/2026-10-07-任務單-產業上限對同產業未估值持股的判定與揭露.md` L277 |
| 6-a PR-2、6-b 總曝險帳本不完整但已超標時不擋加碼 | 舊總綱稱實作可先行，合併上線以 CEO 接受 ADR-0023 前提 4 為閘門 | 舊總綱 §3.2 |
| F-7、F-8、F-10 | F-7 draft（排 PR-RK4c 之後）；F-8 spec（低優先）；F-10 draft（與 F-8 併同一輪驗收） | 各任務單 L3 |
| F11-W38 任務單本體 | 任務單狀態行為 spec；決策包稱已合併，已列 §1 | `work/dispatch/2026-10-13-任務單-F11-W38-…` |
| KT-R-31／32／34（`oos_end`、分段列不得帶全樣本 delta、測試） | 待辦，dev-lead，排程待 CEO；觸發點＝第一份引用偏誤研究結果的報告交給 CEO 或 qa 之前 | KT-1 任務單 L37 |
| ADR-0024 剩餘知悉項 | 決策包稱仍待 | 決策包第四節 |

---

## 6. 維護規則與變更紀錄

維護規則：
1. 每次有項目合併、審查結論改變、CEO 回覆待決項時更新，並在本節追加一行。
2. 狀態只能往有依據的方向移動；移到「已完成」必須附 commit 或 accepted 文件，**不得把規劃中的項目標成完成**。
3. 「待合併」項目的卡點若為 Codex 缺席，在 CEO 決定前一律維持待合併。

變更紀錄：
- 2026-10-16：初版（product-manager，T1-04）。
- 本版的已知缺口：§5 的項目沒有核實；§1 的「已合併」引自決策包而非 git 紀錄；ADR-0004、ADR-0012 檔頭修訂指標未逐檔核對。
