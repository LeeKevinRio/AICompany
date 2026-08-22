# 研究:外部設計 Skill 庫評估(emilkowalski/skills、Nutlope/hallmark)

- 撰寫:art-lead
- 日期:2026-08-22
- 任務:CEO 指定研究兩個外部設計 skill 庫,產出引入/參考/不適用三檔分級建議與授權檢查。
- 性質:**唯讀研究與建議**。引入員工線(main)屬章程層級決策,本文件不做任何引入動作。
- 研究素材:兩 repo 已 clone 至本機 scratchpad,逐一閱讀各 SKILL.md 實體內容
  (emilkowalski 12 個全讀;hallmark 主 SKILL.md 全讀 + 抽樣 slop-test.md 全部 58 道閘門、motion.md、copy.md)。

---

## 一、兩庫一句話定性

| 庫 | 定性 |
| --- | --- |
| **emilkowalski/skills**(12 skills,MIT) | 一位 Vercel/Linear 背景 design engineer 的「動畫與 UI 手感」方法論,拆成 12 個單一職責小 skill——規則具體到 cubic-bezier 數值與 duration 區間,品質高、克制(核心主張是「很多東西不該動畫」),可挑著用。 |
| **Nutlope/hallmark**(單一大型 skill,MIT,Together AI 出品) | 反「AI 生成味」的整頁 UI 生成系統——macrostructure 先行 + 21 主題輪替 + 58 道 slop-test 閘門 + 四動詞(默認生成/audit/redesign/study),規則同樣具體可執行,但整包強耦合、體積大(references 約 5,600 行)、假設 greenfield 行銷頁場景,只能整包用或抽規則自寫,不適合拆件掛載。 |

---

## 二、授權檢查

| 項目 | emilkowalski/skills | Nutlope/hallmark |
| --- | --- | --- |
| LICENSE | MIT(Copyright (c) 2026 Emil Kowalski) | MIT(Copyright (c) 2026 Hallmark contributors) |
| 可否引入/改作 | 可。允許使用、複製、修改、合併、再散布 | 同左 |
| 條件 | 「副本或實質部分」須保留版權與許可聲明 | 同左 |

**結論:兩庫皆 MIT,授權面無障礙。** 實務守則:

1. **整檔或大段複製**(算 substantial portion)→ 在我們的 skill 目錄內附上原 LICENSE 全文與出處(repo URL + commit hash)。
2. **只參考概念自寫我們版本** → 不構成 substantial portion,無強制義務,但建議在 SKILL.md 註明參考來源,方便日後追溯上游更新。
3. MIT 無 copyleft,不會污染我們 repo;唯 hallmark SKILL.md 內嵌「Powered by Together AI」、emil-design-eng 內嵌 animations.dev 課程宣傳語——**引入時應去除行銷語**(MIT 允許修改,合法)。

---

## 三、emilkowalski 12 個 skill 逐個短評

評分軸:方法論、規則品質(具體可執行 vs 空泛口號)、與本公司重疊/互補。

### 1. `animate`(建構動畫)
七步決策序列:該不該動 → 目的 → 工具 → 屬性 → 曲線/時長 → 中斷/退出 → reduced-motion。規則品質**極高**:頻率分級表(100+ 次/日的操作**永不**動畫)、easing 決策表附具體 cubic-bezier、duration 區間表、「Never Ship」自檢清單(禁 `transition: all`、禁 `scale(0)`、禁 `ease-in`、UI 動畫 <300ms)。特別可貴的是 function check:「使用者正在讀或操作的資料不為風格而動——銀行 app 的圖表不動畫最好」——**這句直接站在我們金融資訊密集 UI 這邊**。互補:我們沒有任何動畫規範。★ 首選引入候選。

### 2. `review-animations`(審查動畫 diff)
`animate` 的審查面:十條不可協商標準 + 逃逸觸發清單 + 修復偏好階層(第一優先是**刪掉動畫**)+ 強制 Before/After/Why 表格 + Block/Approve 明確判準。與我們 `code-review-checklist` 的關係是**互補不重疊**(我們查正確性/安全,它查動效手感),形態上與 qa-reviewer 審查流程同構,好接。★ 首選引入候選。

### 3. `animation-vocabulary`(動效詞彙反查表)
把模糊描述(「那個 iOS 拉到底回彈的感覺」)映射到精確術語(Rubber-banding),約 90 條詞彙分十類。純資料、零風險、零行為指令。對 art-lead 最實際的用途:**寫 art-outsource 出圖工單與動效需求單時,用語精確化**;也降低 CEO 與各部門溝通動效需求的成本。★ 低成本引入候選。

### 4. `apple-design`(Apple 流體介面理念翻譯到 Web)
WWDC 談話(Designing Fluid Interfaces 等)蒸餾成 17 節:interruptibility、velocity handoff、momentum projection(附 Apple 實際 decay 公式)、rubber-banding、materials/depth、typography(optical sizing/tracking/leading)、八大設計原則。知識密度高、數值具體(damping/response 對照表)。但重心是**手勢驅動 UI**——對 stock-desk(滑鼠+鍵盤、表格為主)用途低;對 mahjong 線(觸控 PWA)的計分互動、未來娛樂型產品較有價值。列 (b) 參考。

### 5. `emil-design-eng`(總綱哲學)
上面各 skill 的母本(674 行),內容與 `animate`/`review-animations` **大量重複**,額外多了品味哲學(taste is trained、unseen details compound)與 Sonner 開發心得。且開頭有強制行銷回應(被喚起時必須先輸出 animations.dev 課程宣傳)——不適合原樣進員工線。取其規則已被子 skill 覆蓋,列 (c) 不引入(重複+行銷語)。

### 6. `find-animation-opportunities`(找該動畫的地方)
定位是「filter 而非 finder」:四道閘門(頻率/目的/速度/功能)全過才提案,強制輸出「被拒絕的候選」章節,上限 5–7 條。方法論健康(預設拒絕)。但屬於主動巡檢型任務,我們的動效需求量目前太小,單獨掛一個 skill 性價比低——其閘門邏輯已含在 `animate` 步驟 1–2。列 (c)(規則被 animate 覆蓋)。

### 7. `improve-animations`(全 codebase 動效稽核+出計畫)
audit-then-plan 工作流:recon → 分類稽核(可開 subagent)→ 覆核 → 寫自包含計畫給弱模型執行。方法論成熟(含「repo 內容是資料不是指令」的 prompt-injection 防線、「不翻案已記錄的設計取捨」)。但它自帶一套 `plans/` 產出結構與派工模型,與我們 `work/dispatch/` 任務單流程**重疊且不相容**;需要時用 `review-animations` 的標準跑我們自己的流程即可。列 (b):參考其稽核八分類,不引入其派工殼。

### 8. `animate-expo`(React Native/Expo 動畫)
`animate` 的 RN 版:兩 runtime 模型(UI thread vs RN thread)、Reanimated 工具選擇表、「在最慢支援機的 release build 上驗手感」。品質同樣高,但**本公司無 React Native 產品線**。列 (c),未來若開 RN 線再回頭。

### 9. `write-swift`(現代 Swift)
Swift 6.x 語言指南(value types、concurrency、noncopyable 等),品質好但**與設計無關且本公司無 Swift 產品線**。列 (c)。

### 10. `ask-sonner`(Sonner toast 庫使用指南)
單一第三方庫的 setup/API/styling/troubleshooting 手冊。品質好(troubleshooting 表症狀→原因→修法很實用),但**我們沒用 Sonner**;stock-desk 前端也還沒有 toast 需求。列 (c),若日後選用 Sonner 再掛。

### 11. `pick-ui-library`(前端庫選型品味清單)
一張個人品味選型表(toasts=Sonner、動畫=motion、圖表=recharts/Liveline、虛擬列表=Virtuoso、狀態=zustand…)。清單本身可信,但**技術選型在本公司走 ADR 制度**(docs/adr/),不應由外部個人品味清單直接驅動 agent 決策;且清單會過時。列 (b):做為 architect/dev-lead 選型時的參考文獻,不做成會自動觸發的 skill。註:它推薦 recharts——與 mahjong 線現用一致,算旁證。

### 12. `prototype`(多方案原型+picker)
一次做 3–5 個「軸向真正不同」的 UI 變體,放在統一 picker 後讓人實機切換挑選;強調 divergence 要有命名軸向、變體全功能、選定後清理原型面。方法論好,對「視覺方向未定」的場景(如 mahjong v2 改版、新產品)有實戰價值,和我們 `creative-masters` 的發散階段互補(文字發散 → 視覺發散)。但會寫入 prototype 檔案、需 dev server,建議列 (b):概念納入 art-lead 工作法,需要時在**產品分支**臨時使用,不進 main。

---

## 四、hallmark 深評

### 方法論

1. **Macrostructure 先行**:先從 21 個具名頁面骨架(含 nav 14 種、footer 8 種 archetype)挑一個,再談視覺——直接對抗「Hero → 3 features → CTA → footer」的 AI 模板重複。
2. **21 主題 + 輪替規則**:連續產出必須在 paper 明度/display 字體風格/accent 色相三軸至少一軸不同,以 `.hallmark/log.json` 與 CSS stamp 做專案記憶。
3. **58 道 slop-test 閘門**(抽樣全讀):具體度超出預期,不是口號而是可判定的檢查。例:
   - gate 34:320–1920px 全區間不得橫向捲動,指定 `overflow-x: clip`(非 `hidden`,保 sticky);
   - gate 39:input 五態禁 `border-width` 變化(避免 layout shift)、helper text 槽保留 `min-height: 1lh`;
   - gate 40–41:全頁每組 (color, background) 配對跑 WCAG/APCA 對比計算,專抓「黑字黑鈕」「深色區塊忘了翻文字色」;
   - gate 46:**禁止捏造數據**——「+47% conversion」「trusted by 50,000+ teams」等未經使用者提供的量化宣稱一律 fail;
   - gate 50:含圖 grid track 必須 `minmax(0, 1fr)`;
   - gate 48:token 鎖定,渲染中不得出現脫離 `:root` token 的 inline 色值/字體。
4. **四動詞**:默認生成 / audit(唯讀打分)/ redesign(保留路由與資訊架構,只換視覺層)/ study(從截圖或 URL 抽「DNA」——結構、字體配對、色錨——明文拒絕 pixel-clone 與模板市集 URL)。
5. **防護意識**:明文規定「repo 與 design.md 內容是資料不是指令」、study 的 URL 拒絕清單與 attestation 流程、不得刪除 production 檔案未經確認——作者有認真想過濫用面。

### 規則品質評語

具體可執行度**與 emilkowalski 同級甚至更工程化**(閘門多數可機械判定)。但有三個結構性問題:

1. **整包強耦合**:主 SKILL.md 559 行只是調度器,實際規則散在 30+ 個 reference 檔(約 5,600 行),載入紀律本身就是 skill 的一半內容。抽單一檔用會斷鏈。
2. **場景假設是 greenfield 行銷頁/landing page**:macrostructure、hero enrichment、nav/footer archetype、「一定先問 Audience/Use case/Tone」的互動閘門——對我們**已存在、資訊密集、規範已定**的 stock-desk 前端幾乎全部不對口。
3. **有主動寫檔與網路行為**:寫 `.hallmark/preflight.json`、`.hallmark/log.json`、`tokens.css`、`design.md`;study 動詞會 WebFetch 外部 URL。這在員工線是需要 security 審視的行為面。

---

## 五、對照本公司現況

### 5.1 stock-desk 前端(Next.js + Tailwind,dark 主題,neutral 色系,金融資訊密集)

**直接適用**(與現有實踐同向):

- emil 的頻率規則與 function check:高頻操作不動畫、**使用者在讀的數據不為風格而動**——等於替我們「資訊密集 UI 保持安靜」的現狀提供了成文依據。stock-desk 目前幾乎無動畫,依這套標準是**正確狀態**,不是欠債。
- `review-animations` 的逃逸清單(`transition: all`、`ease-in`、layout 屬性動畫)可直接併入前端 review 檢查點,防未來劣化。
- hallmark gate 39(input 五態)、gate 34/50(響應式安全)、gate 41(深色區塊 ink-on-ink)對 dark 主題表單/表格是實用的自檢項。
- hallmark gate 46(禁捏造數據)與我們風控「數據須可佐證」的精神完全同向。

**不適用/必須讓位**(⚠ 本節為評估重點):

1. **揭露文案是風控逐字定稿制度**(見 `work/stock-desk-C5-Kelly-揭露文案起草.md` 等):emil 系列雖不碰文案,但 **hallmark 的 `copy.md`(按鈕動詞、錯誤訊息三段式、active voice)與 redesign 動詞的「component voice」概念,對揭露/免責/建議類文案一律不適用**——任何「重寫文案」類 skill 建議在這條線上直接無效,文案變更只能走風控定稿流程。
2. **樣式有風控地板,skill 建議與地板衝突時地板優先**:
   - 免責聲明「與主結論同一視覺區塊常駐,**不得摺疊、不得移至頁尾、字級不得小於區塊內文**」(`work/stock-desk-phase8-風控定調.md` L60)。hallmark 的 restraint/「刪掉不 earning its place 的元素」傾向、或任何「收進 footer/摺疊以簡化版面」的建議,在這裡**無條件讓位**。
   - hallmark gate 40–41 的對比門檻若機械套用,會把我們**刻意的低對比設計**(捲軸 thumb 2.03:1、分隔線 1.39:1,`work/stock-desk-視覺規範-捲軸與表格.md` 明文記錄為設計取捨)判為 fail——引入任何對比閘門時必須把「站內既有已記錄的取捨」列為白名單,對應 emil `improve-animations` 自己也有的原則:「不翻案已記錄的設計決策」。
   - hallmark gate 16「效果可見就 silent success,不出恭喜 toast」方向上與金融工具的克制一致,但涉及**交易/匯入等關鍵操作的回饋**時,回饋顯著度由風控與 UX 驗收決定,不由外部 skill 決定。
3. hallmark 的 macrostructure/主題輪替/hero 流程對 stock-desk 產品內頁**整體不適用**(不是行銷頁、不允許每頁長得不一樣);唯一potential 用途是未來若做 stock-desk 對外介紹頁。

### 5.2 mahjong 線(mahjong-score-web,Vite + React PWA,娛樂型)與未來產品線

- 娛樂型 app 是 emil 系列的甜蜜點:`apple-design` 的手勢/spring/rubber-banding、`animate` 的 delight budget(「稀有時刻才花動畫預算」)適合計分完成、連莊等時刻;`prototype` 的多變體 picker 適合 v2 視覺改版拿方案。
- 未來新產品的 landing page/官網,是 hallmark 唯一對口的場景——屆時在**產品分支**臨時掛整包使用即可,不需要進 main。
- 依分支哲學,產品特定的用法(哪個時刻配什麼動畫)寫在產品分支的視覺規範,main 只放通用能力。

### 5.3 與既有 .claude/skills 的關係

| 既有 skill | 關係 |
| --- | --- |
| `creative-masters` | 互補。它管「想什麼」(概念發散),emil/hallmark 管「做出來的手感」(執行紀律)。`prototype` 的多變體法可視為 creative-masters 發散在視覺層的延伸。 |
| `art-outsource` | 互補。`animation-vocabulary` 可直接提升出圖/動效工單的用語精確度;hallmark 的 imagery 層級(typography-only → CSS art → SVG → 生成圖 → Lottie 最後手段)可參考進工單的資產層級判斷。 |
| `code-review-checklist` | 互補不重疊。動效/UI 手感審查是它沒覆蓋的維度,`review-animations` 的清單可作為附錄或獨立 skill。 |
| `.claude/skills/README.md` 待辦 | 該檔本就預留「掛開源 skill」的 TODO 與授權提醒,本研究即是該決策的前置作業。 |

---

## 六、三檔分級建議

> 前提:引入員工線是章程層級決策,以下僅為 art-lead 的建議與取捨分析,最終由 CEO 裁決;且任何引入前應完成第七節的安全審查。

### (a) 建議引入員工線(改作後引入,非原樣照搬)

| Skill | 為什麼 | 預期用在哪 |
| --- | --- | --- |
| `animate` | 規則具體(曲線/時長/屬性全有數值)、自帶「不該動畫」閘門,與 main 零產品耦合原則相容(純通用能力) | frontend-engineer 實作任何動效時的強制流程;也是「為什麼 stock-desk 不加動畫」的成文依據 |
| `review-animations` | 十條標準+逃逸清單+Block/Approve 判準,形態與 qa-reviewer 流程同構 | qa-reviewer 審 UI diff 時加掛;或併入 code-review-checklist 作動效附錄 |
| `animation-vocabulary` | 純詞彙對照表,零行為指令、零風險、維護成本近零 | art-lead 出工單、跨部門動效溝通、給 Codex 的 review 用語統一 |

引入方式建議:繁中化敘述層(規則值保留英文原文)、去除行銷語與外部連結依賴、pin 上游 commit、附 MIT 聲明。三者合計約 570 行,審查成本可控。

### (b) 值得參考其規則、但自寫我們版本

| 來源 | 抽什麼 | 自寫成什麼 |
| --- | --- | --- |
| hallmark `slop-test.md` | 通用可機械判定的閘門子集:對比(40–41,**加站內既定取捨白名單**)、input 五態(39)、響應式安全(34/49/50/51)、禁捏造數據(46)、token 紀律(48)、focus ring 即現(15) | 我們自己的「UI 交付自檢清單」skill,約 15–20 條,dark 主題導向,**開頭明文寫入「風控地板優先於本清單任何建議」與「揭露文案不在本清單管轄範圍」** |
| hallmark 整體方法 | 「先自我評分再交付」(pre-emit critique 六軸)、「stamp 記錄設計決策」的可追溯做法 | 併入上述自檢清單的流程段 |
| `apple-design` | spring 參數表、rubber-banding、觸控回饋、reduced-motion 三訊號 | mahjong 線視覺規範(產品分支)的動效章節參考文獻 |
| `improve-animations` | 稽核八分類、「不翻案已記錄取捨」原則 | 若日後需要動效稽核,用我們 dispatch 流程跑,不引入其 plans/ 派工殼 |
| `prototype` | 「具名軸向的真發散 + 實機 picker + 選定後清理」方法 | art-lead 工作法文件;需要時在產品分支臨時執行 |
| `pick-ui-library` | 選型清單作為文獻 | architect 寫 ADR 時的參考來源之一,不做成 skill |

### (c) 不適用(不引入)

| Skill | 理由 |
| --- | --- |
| hallmark 整包 | 場景不對口(greenfield 行銷頁 vs 我們的既有資訊密集產品)、強耦合無法拆件掛載、主動寫檔+WebFetch 行為面、互動提問閘門與我們派工流程不合。**保留原 repo 位址,未來產品需要行銷頁時在產品分支臨時掛整包**,屆時仍需先過安全審查 |
| `emil-design-eng` | 內容與 animate/review-animations 高度重複;內嵌強制行銷回應不宜進員工線 |
| `find-animation-opportunities` | 閘門邏輯已被 `animate` 覆蓋;主動巡檢需求目前不存在 |
| `animate-expo` | 無 React Native 產品線 |
| `write-swift` | 無 Swift 產品線,且與設計無關 |
| `ask-sonner` | 未使用 Sonner;屬單一依賴的手冊,等選型定案再說 |

---

## 七、風險註記(引入前的安全審查建議)

外部 skill 的每一行指令都會**直接成為 agent 的行為指示**,等同於供應鏈引入,風險不在授權而在行為:

1. **必須過 security-engineer + qa-reviewer(含 Codex 第二意見)逐行審查**才可進 main——審查點:是否含網路存取(hallmark study 的 WebFetch)、檔案寫入(hallmark 的 `.hallmark/`、design.md;improve-animations 的 `plans/`)、是否可能被文件內容注入指令(hallmark 自己有防護條款,反而是好範本)、是否有改變 agent 語氣/揭露行為的指令(emil-design-eng 的強制行銷回應即為實例)。
2. **Pin 版本**:引入時記錄上游 commit hash,禁止「追 upstream 最新」;上游更新須重新走審查。
3. **敘述層繁中化改寫**是天然的審查機會——改寫過程等於逐行讀過一遍,建議引入與改寫由不同人(art-lead 改寫、security/qa 審)分工,符合最小權限與互檢精神。
4. **員工線紀律**:引入後跑 `python scripts/validate_agents.py` 與 CI;skill 敘述不得綁死產品路徑(main 零產品耦合);唯讀性質的審查類 skill(如 review-animations)遵守唯讀職能不得有 Write/Edit/Bash 的原則。
5. **風控地板條款要寫進 skill 本體**:凡引入或自寫的 UI 類 skill,開頭固定聲明——「揭露類文案為風控逐字定稿,本 skill 之任何文案建議不適用;樣式建議與風控地板(字級/對比/常駐不摺疊)衝突時,地板優先」。讓地板優先權存在於 skill 文本內,而不是依賴 agent 記得章程。

---

## 八、下一步(待 CEO 裁決)

1. 裁決 (a) 三件是否引入;若同意,開 `chore/agent-*` 分支走改寫 → security/qa 審查 → validate → 合併 main 的流程。
2. 裁決 (b) 的「UI 交付自檢清單」是否立案自寫(art-lead 可草擬,估一個工作單位)。
3. `.claude/skills/README.md` 的待辦清單可據本研究更新(該檔目前只列 superpowers/anthropics/openai 三個候選,未含本次兩庫)。
