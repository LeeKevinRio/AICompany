# C5 Kelly — 條件 46 原始回測值查看路徑裁決(tech-architect)

- **日期**:2026-08-22
- **依據**:風控第三輪條件 21、第六輪條件 42/46;FR-6 (fr6-overridden) 定稿「原始回測帶入的數字仍保留、可以查看」

## 三項裁決(結論先行)

1. **採 (a1)——設定頁 KellyInputsSection 卡片內的互斥檢視切換**(生效值檢視 ↔ 原始值檢視,兩態不得同時渲染於 DOM)。否決 (b) 並列;否決 (a) 弱形式 accordion 追加展開(展開後實質並列,且與 repo 既有「揭露移出 details」判例衝突)與 modal 疊層(bg-black/60 底層仍可讀、DOM 保留生效值,「同屏與否」淪為主觀)。
2. **條件 21 區辨句不觸發,但仍有 1 句新文案**:覆寫列的原始值在既有 32 句中無合法搭配((e) 掛錯 BLOCKING/(e-manual) 對原始值不實/不掛違反 required 4)——與並列與否無關;(a1) 把它從高難度區辨句降級為一句短「原始值標示句」。**不背書「無殘項」**。
3. **不出具「同屏兩欄」證明**:策略/Buy&Hold 兩欄僅存在於 /backtest 的 SegmentTable,與 Kelly 明細不同路由不同元件;且 kelly_inputs 完全不落地任何 Buy&Hold 指標,要有就得改 schema 開新 ADR——**行使否決**。creative「Kelly 情境版重擬」為唯一路線;既有 api/backtest.py 常數不動。

## 架構理由

真正的問題不是「放哪裡」,是**每一句已定稿揭露的指涉集合必須唯一**。同一可見面同時存在「系統量測值」與「使用者手鍵值」兩種語意的勝率,畫面只掛得住其中一句。互斥檢視在渲染層消掉矛盾,不靠文字補救——最小文案面原則的正確落點。**不改 ADR-0006**(accepted 不得原地改寫);本裁決不引入新端點/表/模組邊界(KellyInputView 已含完整 row,backtest_* 前端已可得);若要把「不得同屏」固化為長期不變式可另開 ADR-0007(新增 UI 不變式,不 supersede)。

## 對實作的約束(K4c,逐條可檢查)

**位置與可達性**
1. 原始值檢視只存在於設定頁 KellyInputsSection;不得出現在 LimitsCheckList 或 /backtest 頁。
2. 入口僅在 `source === "backtest_overridden"` 且 backtest_win_rate/backtest_payoff_ratio 皆非 null 時渲染;其餘**不渲染**(非 disabled 非灰階)。manual 恆 null;backtest 原始值=生效值,顯示入口即誤導。
3. 兩態互斥:原始值檢視開啟時,生效值欄位、(e-manual)、(f)(含 tooltip)不得存在於 DOM;反之亦然。qa 雙向 queryBy* null 斷言。
4. 禁 `<details>/<summary>` 追加展開與 `role="dialog"` 疊層。卡片標頭(標題、FR-4 徽章、FR-6 來源標籤)可跨兩態常駐(無勝率數值)。
5. 返回控制項常駐可見,不得只靠 ESC/點外部。

**欄位集(最小且封閉)**
6. 原始值檢視**只准**三項:backtest_win_rate、backtest_payoff_ratio、OOS 起訖日期(帶日期理由:1-A 指涉可查證;兩日期對覆寫列本已是可見事實(計齡錨+g-3),非新增資訊;不構成條件 42 的「11 欄明細區塊」)。
7. **明文禁止**出現(每項都拖出新文案依賴):strategy_id/策略欄、五項回合計數與 oos_observations(觸發 43/44/(h))、p_ci_*/f_star/f_star_ci_*(觸發條件 6/(a))、k_observed_at_write(觸發 (b))、rates_verified(欄位 10)、dividend_reason_code/adjust_dividends(欄位 11 退修中)、produced_at(D-4 非錨,顯示誘發誤讀)、low_sample_warning、spec_hash/bootstrap_*。
8. 不得渲染成表格式「明細」外觀;三項以簡單標籤-值列呈現。

**文案面(交 creative 新擬 1 句送風控)**
9. 「原始值標示句」三要件:①這兩個數字是回測帶入當時由系統算出、之後被你手動調整而仍保留的原始值;②目前生效的是你調整後的數字,不是這裡這兩個;③本條上限的計算用的是生效值,不是這裡的數字。(三點皆經 overriding 與 D-2「上限一律以生效 p/b 重呼叫」查證為真。)
10. OOS 日期標籤不得逕自複用 FR-5 欄位 2 CONFIRMED 標籤(會被讀為 FR-5 明細);標籤字面隨標示句送審。
11. 該檢視所有中文字面(含「勝率」標籤)一律後端常數、前端逐字渲染;「勝率」由風控依條件 48 擴充白名單;常數放 kelly_wording.py,逐字守門同 commit。
12. 數值渲染沿用生效值同套格式:固定位數、禁 :g、禁科學記號、禁 inf/-inf/nan/None/null 字面。
13. 條件 42 不變:覆寫列不顯示 FR-5 明細;backtest 列照常顯示且不得出現本入口。

**驗收**
14. 單元四情境:manual(無入口)/backtest(無入口)/overridden+非 null(有入口)/overridden+null(無入口,理論不可達仍斷言)。
15. qa-e2e:覆寫列切入原始值檢視截圖證明生效值與 (e-manual)/(f) 不存在;切回後原始值消失。
16. 反向守門:原始值檢視渲染樹中禁用欄位(第 7 條)任一出現即紅燈。

## 附帶發現(轉風控)

**(g) 句覆寫列來源標籤缺口**:backtest_overridden 的新鮮度錨仍是 oos_end_date(models.py:360-364),但 (g-2) 寫「來源：手動輸入」、(g-3) 寫「來源：回測帶入」,兩句皆未涵蓋「回測帶入、已手動調整」態。今日不可達(條件 19 未結),條件 19 一落地即可達。建議 K4 落地前釐清,避免重演掛錯即 BLOCKING。

---

# 附註|約束 37 讀法追認(2026-08-22,tech-architect)

**追認** K4b-backend 的邊界讀法(book.py 只 import `app.kelly.models`;limits.py 對 app/kelly 零 import)。理由:約束 37 真正要防的是演算法唯一性被複製、閘門吃到回測型別、循環依賴;`advice → kelly.models` 是對純資料模型+純函式的單向依賴(無 I/O、無循環、不觸及 kelly_fraction),三受詞不受影響。替代方案均不採:抽共用層=為一個函式開第四模組且規則與型別分家;api 算好傳入=把「無錨即過期」執行點分散到每個呼叫端,更差。

**收緊三項**:
1. 約束 37 補例外明文並更正箭頭圖(已由協調人落檔於架構評估)。
2. **守門測試兩個洞(退 dev 補強)**:test_advice_book.py:814-829 只 walk `ast.ImportFrom`(`import app.kelly.store` 寫法掃不到)且掃描面僅 book.py 一檔——limits/context/engine/book_limits 日後 import store 不會紅燈;約束 12「limits.py 對 app/kelly 零 import」目前無測試釘。改用既有 tests/import_graph.py 的傳遞閉包(同 test_kelly_boundary 機制)對整個 app/advice 套件斷言 `app.kelly.store`/`app.kelly.attempts` 不可達,並加 limits.py 零 import 白盒斷言。
3. `ageing_of` 的 now 維持 keyword-only 注入、`app.kelly.models` 維持不讀時鐘不碰 DB(現況合規);讀時鐘唯一位置=book.py builder。
