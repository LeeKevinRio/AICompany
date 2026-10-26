# 任務單：FD-2 出發地／目的地中文輸入建議

- 狀態：done（待 CEO 驗收）
- 發起人：CEO
- 目前負責：CEO
- 相關文件：`work/flight-deals-FD-2-PRD.md`、`work/flight-deals-PRD.md`（FD-1，修訂其 FR-A1／FR-A4 出發地目的地部分）、`work/tasks/FD-1.md`、`docs/adr/0002-flight-deals-技術棧與資料源.md`（accepted；D-1、C-14、C-17 為本任務約束）

## 目標

CEO 原話：「可以的話補上我打上什麼中文，你會有個提示下拉，我可以快速選。例如我找『東』，下拉選單就會有東京之類的。不一定要用代碼來找機場。」

出發地與目的地欄位改為輸入即建議：可用中文、英文或代碼片段搜尋，下拉顯示「中文名 代碼（補充）」，選取後欄位值為 IATA 代碼並顯示中文名。支援機場與城市兩種層級；城市代碼須逐筆標記「已驗證可查」才開放。資料為內建精選對照表（約 200 至 400 筆），不靠外部 API、不新增執行期依賴。後端只接受表內代碼，表外回 422「請從下拉選取」。列表、詳情、Telegram 推播的路線改顯示為中文＋代碼。範圍外：多語系、模糊拼字修正、全球所有機場、機場群組自訂。

## 驗收條件

完整 Given/When/Then 見 PRD「驗收條件」章節（AC-D1 至 AC-C1，對應五塊需求：資料、查詢與排序、表單下拉、顯示、驗證）。摘要：

- 打「東」出現東京、成田、羽田；打「nrt」出現成田且排第一；打「ZZZ」無結果，直接送出被後端 422 拒絕。
- 排序：代碼完全命中 > 中文前綴 > 英文前綴 > 包含。
- 鍵盤可操作（上下、Enter、Esc）；375px 寬度無橫向捲動且可點選。
- 選取後值為 IATA 代碼並顯示中文名。
- AC-F9（停用 JavaScript 仍可手打代碼送出）：**不適用**——表單自 FD-1 起即由 JS 送出且 CSP `form-action 'none'`，總經理 2026-10-26 降級。
- 城市代碼逐筆標記已驗證可查（TYO、OSA 已實測可查；LON 實測失敗，不開放，只列其機場）。
- 列表、詳情、推播顯示「台北 TPE → 東京成田 NRT」；推播字數克制。
- FD-1 既有監看照常運作，代碼不在表內者顯示退回只顯示代碼。

tech-architect 評估關卡需回覆：

1. 對照表存放形式、前端下拉做法（遵守 D-1 不加框架、C-14 不用 CDN）、建議由前端比對或後端端點（PRD 開放問題 5、6）。
2. 結果筆數上限、同順位內排序、城市驗證的批次實測方式與頻率控制，以及 LON 失敗是否需釐清（PRD 開放問題 5、7）。
3. 是否需要 ADR（對照表資料結構、驗證模型變更若與 accepted ADR-0002 有衝突，以 ADR 為準並出補充）。
4. 評估通過才可推進至 `build`；若認為某需求不可行，須退回 product-manager 並附理由。

待 CEO 回覆的產品取捨：PRD 開放問題 1 至 4（空欄位是否列常用項、同城市組合是否拒絕、舊監看修改時是否須重選、想優先驗證的城市）。皆已有預設值，CEO 未覆議則照預設。

## 交接紀錄

- 2026-10-26 product-manager → tech-architect：FD-2 PRD v0.1 與驗收條件已定（依總經理定調），請評估可行性；PRD 開放問題 1 至 4 待 CEO，5 至 7 待 tech-architect，8 待 dev-lead，9 待 qa-e2e。
- 2026-10-26 tech-architect → 總經理：評估通過，不另開 ADR，增補小節與 C-19～C-25 已落進 ADR-0002；開放問題 5～7 已答（伺服端搜尋、A1 常數表、LON 不開放、其他城市由 dev-lead 批次實測）。
- 2026-10-26 總經理：開放問題 1～4 採預設（不列常用項、同城市拒絕、舊監看修改須重選、城市由 dev-lead 實測開放）；TPE 短名「台北桃園」。狀態 spec → build，dev-lead 與 frontend-engineer 並行。

## 對照表逐筆查證表（C-23，dev-lead，2026-10-26）

- 對照表：`apps/flight-deals/src/flight_deals/domain/airports.py` 的 `PLACES`，共 122 筆（機場 114、城市 8）。
- 查證方式（三源交叉，全部 122 筆都查，不是抽查）：
  1. **IATA 官方查詢頁**：逐筆以 `https://www.iata.org/en/publications/directories/code-search/?airport.search=<code>` 查詢（每筆間隔 1 秒），122/122 皆查得該代碼且城市與名稱相符；城市碼（TYO、OSA、SPK、SEL、BJS、NYC、LON、PAR）於官方頁標為 Metropolitan Area。
  2. **英文維基「List of airports by IATA code: A–Z」**：122/122 代碼列存在且機場名稱、所在城市相符；城市碼列皆有 metropolitan area 註記，並依其註記確認城市所轄機場（例：OSA＝KIX、ITM、UKB，因此 UKB 歸入 OSA）。
  3. **中文維基條目**：機場 114 筆經 Wikidata（P238 IATA 代碼）取得中文維基條目，抓條目原始碼確認 infobox `IATA =` 欄位與代碼一致，112 筆自動比對相符；FOC（infobox 寫成 `{{lang|en|FOC}}`）與 IAH（infobox 無 IATA 欄，`pushpin_label = IAH`）2 筆人工確認相符。中文名稱以台灣慣用譯名為準，必要時加上城市前綴以便辨識（例：「東京成田國際機場」）。
- 撞碼處理：TPE、HKG、SHA、BKK、SIN、KUL、MNL、SYD、MEL、AKL、GUM、LAX、SEA、DFW、BOS、PHX、YVR、FRA、MUC、PRG、MAD、IST、DXB、NGO、OKA 在 IATA 同時是城市碼與機場碼，依 ADR 只保留機場列。

### 城市代碼可查性實測（FR-D3）

批次：2026-10-26 08:24 UTC，fast-flights 3.1.0，TPE→X 單程、2026-12-10、max_stops=1、每次間隔 2 秒，只跑一次。

| 代碼 | 結果 | 結果中的目的機場 | 判定 |
|---|---|---|---|
| SEL | 成功（11 筆） | GMP、ICN | 城市列 `city_query_verified=True` |
| BJS | 成功（3 筆） | PEK、PKX | 城市列 `city_query_verified=True` |
| NYC | 成功（6 筆） | EWR、JFK、LGA | 城市列 `city_query_verified=True` |
| PAR | 成功（6 筆） | 只有 CDG | 未含多個機場，城市列 `False`（CDG、ORY 可選） |
| LON | 失敗（IndexError） | — | 城市列 `False`（與總經理先前實測一致；LHR、LGW 可選） |
| BKK | 成功（16 筆） | 只有 BKK | 撞碼，保留機場列 |
| SIN | 成功（10 筆） | 只有 SIN | 撞碼，保留機場列 |
| LAX | 成功（5 筆） | 只有 LAX | 撞碼，保留機場列 |
| HKG | 失敗（IndexError） | — | 撞碼，保留機場列（**注意**：以機場碼查 HKG 本次失敗，見已知限制） |
| SHA | 失敗（IndexError） | — | 撞碼，保留機場列（同上） |
| TYO、OSA | 總經理 2026-10-26 實測成功 | HND/NRT、ITM/KIX | 城市列 `city_query_verified=True` |
| SPK | 未實測 | — | 城市列 `False`（只供「札幌」搜到 CTS） |

### 別名增補查證（第二批，2026-10-26）

| code | 新增別名 | 出處 | 查證日期 |
|---|---|---|---|
| CJU | 濟州島 | [中文維基「濟州島」](https://zh.wikipedia.org/wiki/濟州島)；[濟州國際機場](https://zh.wikipedia.org/wiki/濟州國際機場) 條目內文提及濟州島 | 2026-10-26 |
| HKT | 普吉島、布吉 | [中文維基「布吉國際機場」](https://zh.wikipedia.org/wiki/布吉國際機場)（條目名即「布吉」，內文含「普吉島」）；[普吉島](https://zh.wikipedia.org/wiki/普吉島)（重新導向至「普吉府」） | 2026-10-26 |

### qa-reviewer C-23 抽查結果

- 27 筆依記憶判讀全部一致（含 8 城市列、9 撞碼列、8 歐美機場）。
- 備註：SHA、HKG 等撞碼機場上游解析偶發失敗（SHA 穩定失敗於 fast-flights `parser.py:77`），使用者仍可選取，待辦 FD-3 處理。

### 逐筆明細

| # | code | 層級 | 中文名 | IATA 官方查詢結果（城市 / 名稱） | 中文維基條目（infobox IATA） | 查證日期 |
|---|---|---|---|---|---|---|
| 1 | TPE | 機場 | 台灣桃園國際機場 | OK：Taipei / Metropolitan Area；Taipei / Taiwan Taoyuan Int'l | [臺灣桃園國際機場](https://zh.wikipedia.org/wiki/臺灣桃園國際機場) OK | 2026-10-26 |
| 2 | TSA | 機場 | 台北松山機場 | OK：Taipei / Songshan | [臺北松山機場](https://zh.wikipedia.org/wiki/臺北松山機場) OK | 2026-10-26 |
| 3 | KHH | 機場 | 高雄國際機場 | OK：Kaohsiung / Kaohsiung Intl. | [高雄國際機場](https://zh.wikipedia.org/wiki/高雄國際機場) OK | 2026-10-26 |
| 4 | RMQ | 機場 | 台中國際機場 | OK：Taichung / Cingcyuangang | [臺中清泉崗機場](https://zh.wikipedia.org/wiki/臺中清泉崗機場) OK | 2026-10-26 |
| 5 | TNN | 機場 | 台南機場 | OK：Tainan / Tainan Airport | [臺南機場](https://zh.wikipedia.org/wiki/臺南機場) OK | 2026-10-26 |
| 6 | HUN | 機場 | 花蓮機場 | OK：Hualien / Hualien Airport | [花蓮機場](https://zh.wikipedia.org/wiki/花蓮機場) OK | 2026-10-26 |
| 7 | MZG | 機場 | 澎湖機場 | OK：Penghu / Penghu Airport | [澎湖機場](https://zh.wikipedia.org/wiki/澎湖機場) OK | 2026-10-26 |
| 8 | KNH | 機場 | 金門機場 | OK：Kinmen / Shangyi | [金門機場](https://zh.wikipedia.org/wiki/金門機場) OK | 2026-10-26 |
| 9 | TYO | 城市 | 東京 | OK：Tokyo / Metropolitan Area | —（城市碼；另對照英文維基 IATA 代碼列表 metropolitan area 註記） | 2026-10-26 |
| 10 | NRT | 機場 | 東京成田國際機場 | OK：Tokyo / Narita Intl | [成田国际机场](https://zh.wikipedia.org/wiki/成田国际机场) OK | 2026-10-26 |
| 11 | HND | 機場 | 東京羽田國際機場 | OK：Tokyo / Tokyo Intl (Haneda) | [東京國際機場](https://zh.wikipedia.org/wiki/東京國際機場) OK | 2026-10-26 |
| 12 | OSA | 城市 | 大阪 | OK：Osaka / Metropolitan Area | —（城市碼；另對照英文維基 IATA 代碼列表 metropolitan area 註記） | 2026-10-26 |
| 13 | KIX | 機場 | 大阪關西國際機場 | OK：Osaka / Kansai International | [关西国际机场](https://zh.wikipedia.org/wiki/关西国际机场) OK | 2026-10-26 |
| 14 | ITM | 機場 | 大阪伊丹機場 | OK：Osaka / Osaka Intl (Itami) | [大阪國際機場](https://zh.wikipedia.org/wiki/大阪國際機場) OK | 2026-10-26 |
| 15 | UKB | 機場 | 神戶機場 | OK：Osaka / Kobe | [神戶機場](https://zh.wikipedia.org/wiki/神戶機場) OK | 2026-10-26 |
| 16 | SPK | 城市 | 札幌 | OK：Sapporo / Metropolitan Area | —（城市碼；另對照英文維基 IATA 代碼列表 metropolitan area 註記） | 2026-10-26 |
| 17 | CTS | 機場 | 新千歲機場 | OK：Sapporo / New Chitose | [新千歲機場](https://zh.wikipedia.org/wiki/新千歲機場) OK | 2026-10-26 |
| 18 | NGO | 機場 | 中部國際機場 | OK：Nagoya / Chubu Centrair Intl；Nagoya / Metropolitan Area | [中部國際機場](https://zh.wikipedia.org/wiki/中部國際機場) OK | 2026-10-26 |
| 19 | FUK | 機場 | 福岡機場 | OK：Fukuoka / Fukuoka Airport | [福岡機場](https://zh.wikipedia.org/wiki/福岡機場) OK | 2026-10-26 |
| 20 | OKA | 機場 | 那霸機場 | OK：Okinawa / Naha；Okinawa / Metropolitan Area | [那霸機場](https://zh.wikipedia.org/wiki/那霸機場) OK | 2026-10-26 |
| 21 | KOJ | 機場 | 鹿兒島機場 | OK：Kagoshima / Kagoshima Airport | [鹿兒島機場](https://zh.wikipedia.org/wiki/鹿兒島機場) OK | 2026-10-26 |
| 22 | KMJ | 機場 | 熊本機場 | OK：Kumamoto / Kumamoto Airport | [熊本機場](https://zh.wikipedia.org/wiki/熊本機場) OK | 2026-10-26 |
| 23 | HIJ | 機場 | 廣島機場 | OK：Hiroshima / Hiroshima Airport | [广岛机场](https://zh.wikipedia.org/wiki/广岛机场) OK | 2026-10-26 |
| 24 | OKJ | 機場 | 岡山機場 | OK：Okayama / Okayama Airport | [岡山機場](https://zh.wikipedia.org/wiki/岡山機場) OK | 2026-10-26 |
| 25 | TAK | 機場 | 高松機場 | OK：Takamatsu / Takamatsu Airport | [高松機場](https://zh.wikipedia.org/wiki/高松機場) OK | 2026-10-26 |
| 26 | MYJ | 機場 | 松山機場（愛媛） | OK：Matsuyama / Matsuyama Airport | [松山機場 (日本)](https://zh.wikipedia.org/wiki/松山機場_(日本)) OK | 2026-10-26 |
| 27 | SDJ | 機場 | 仙台機場 | OK：Sendai / Sendai Airport | [仙台機場](https://zh.wikipedia.org/wiki/仙台機場) OK | 2026-10-26 |
| 28 | KMQ | 機場 | 小松機場 | OK：Komatsu / Komatsu Airport | [小松機場](https://zh.wikipedia.org/wiki/小松機場) OK | 2026-10-26 |
| 29 | HKD | 機場 | 函館機場 | OK：Hakodate / Hakodate Airport | [函館機場](https://zh.wikipedia.org/wiki/函館機場) OK | 2026-10-26 |
| 30 | AOJ | 機場 | 青森機場 | OK：Aomori / Aomori Airport | [青森機場](https://zh.wikipedia.org/wiki/青森機場) OK | 2026-10-26 |
| 31 | ISG | 機場 | 新石垣機場 | OK：Ishigaki / Ishigaki | [石垣機場 (初代)](https://zh.wikipedia.org/wiki/石垣機場_(初代)) OK | 2026-10-26 |
| 32 | FSZ | 機場 | 富士山靜岡機場 | OK：Shizuoka / Mount Fuji | [靜岡機場](https://zh.wikipedia.org/wiki/靜岡機場) OK | 2026-10-26 |
| 33 | IBR | 機場 | 茨城機場 | OK：Ibaraki / Ibaraki Airport | [茨城机场](https://zh.wikipedia.org/wiki/茨城机场) OK | 2026-10-26 |
| 34 | HSG | 機場 | 佐賀機場 | OK：Saga / Saga Airport | [佐賀機場](https://zh.wikipedia.org/wiki/佐賀機場) OK | 2026-10-26 |
| 35 | SEL | 城市 | 首爾 | OK：Seoul / Metropolitan Area | —（城市碼；另對照英文維基 IATA 代碼列表 metropolitan area 註記） | 2026-10-26 |
| 36 | ICN | 機場 | 首爾仁川國際機場 | OK：Seoul / Incheon International | [仁川國際機場](https://zh.wikipedia.org/wiki/仁川國際機場) OK | 2026-10-26 |
| 37 | GMP | 機場 | 首爾金浦國際機場 | OK：Seoul / Gimpo International | [金浦國際機場](https://zh.wikipedia.org/wiki/金浦國際機場) OK | 2026-10-26 |
| 38 | PUS | 機場 | 釜山金海國際機場 | OK：Busan / Gimhae Intl | [金海國際機場](https://zh.wikipedia.org/wiki/金海國際機場) OK | 2026-10-26 |
| 39 | CJU | 機場 | 濟州國際機場 | OK：Jeju / Jeju Intl. | [濟州國際機場](https://zh.wikipedia.org/wiki/濟州國際機場) OK | 2026-10-26 |
| 40 | TAE | 機場 | 大邱國際機場 | OK：Daegu / Daegu Intl. | [大邱國際機場](https://zh.wikipedia.org/wiki/大邱國際機場) OK | 2026-10-26 |
| 41 | CJJ | 機場 | 清州國際機場 | OK：Cheongju / Cheongju Intl. | [清州國際機場](https://zh.wikipedia.org/wiki/清州國際機場) OK | 2026-10-26 |
| 42 | HKG | 機場 | 香港國際機場 | OK：Hong Kong / Metropolitan Area；Hong Kong / Hong Kong Intl. | [香港國際機場](https://zh.wikipedia.org/wiki/香港國際機場) OK | 2026-10-26 |
| 43 | MFM | 機場 | 澳門國際機場 | OK：Macau / Macau Intl. | [澳門國際機場](https://zh.wikipedia.org/wiki/澳門國際機場) OK | 2026-10-26 |
| 44 | BJS | 城市 | 北京 | OK：Beijing / Metropolitan Area | —（城市碼；另對照英文維基 IATA 代碼列表 metropolitan area 註記） | 2026-10-26 |
| 45 | PEK | 機場 | 北京首都國際機場 | OK：Beijing / Capital Intl | [北京首都国际机场](https://zh.wikipedia.org/wiki/北京首都国际机场) OK | 2026-10-26 |
| 46 | PKX | 機場 | 北京大興國際機場 | OK：Beijing / Daxing Intl. | [北京大兴国际机场](https://zh.wikipedia.org/wiki/北京大兴国际机场) OK | 2026-10-26 |
| 47 | SHA | 機場 | 上海虹橋國際機場 | OK：Shanghai / Metropolitan Area；Shanghai / Hongqiao Intl | [上海虹桥国际机场](https://zh.wikipedia.org/wiki/上海虹桥国际机场) OK | 2026-10-26 |
| 48 | PVG | 機場 | 上海浦東國際機場 | OK：Shanghai / Pudong Intl | [上海浦东国际机场](https://zh.wikipedia.org/wiki/上海浦东国际机场) OK | 2026-10-26 |
| 49 | CAN | 機場 | 廣州白雲國際機場 | OK：Guangzhou / Baiyun Intl | [广州白云国际机场](https://zh.wikipedia.org/wiki/广州白云国际机场) OK | 2026-10-26 |
| 50 | SZX | 機場 | 深圳寶安國際機場 | OK：Shenzhen / Bao'an Intl | [深圳宝安国际机场](https://zh.wikipedia.org/wiki/深圳宝安国际机场) OK | 2026-10-26 |
| 51 | CTU | 機場 | 成都雙流國際機場 | OK：Chengdu / Shuangliu Intl | [成都双流国际机场](https://zh.wikipedia.org/wiki/成都双流国际机场) OK | 2026-10-26 |
| 52 | TFU | 機場 | 成都天府國際機場 | OK：Chengdu / Tianfu International | [成都天府国际机场](https://zh.wikipedia.org/wiki/成都天府国际机场) OK | 2026-10-26 |
| 53 | XMN | 機場 | 廈門高崎國際機場 | OK：Xiamen / Gaoqi Intl | [厦门高崎国际机场](https://zh.wikipedia.org/wiki/厦门高崎国际机场) OK | 2026-10-26 |
| 54 | FOC | 機場 | 福州長樂國際機場 | OK：Fuzhou / Changle Intl | [福州长乐国际机场](https://zh.wikipedia.org/wiki/福州长乐国际机场) OK（人工確認） | 2026-10-26 |
| 55 | HGH | 機場 | 杭州蕭山國際機場 | OK：Hangzhou / Xiaoshan Intl | [杭州萧山国际机场](https://zh.wikipedia.org/wiki/杭州萧山国际机场) OK | 2026-10-26 |
| 56 | NKG | 機場 | 南京祿口國際機場 | OK：Nanjing / Lukou Intl | [南京禄口国际机场](https://zh.wikipedia.org/wiki/南京禄口国际机场) OK | 2026-10-26 |
| 57 | CKG | 機場 | 重慶江北國際機場 | OK：Chongqing / Jiangbei Intl | [重庆江北国际机场](https://zh.wikipedia.org/wiki/重庆江北国际机场) OK | 2026-10-26 |
| 58 | XIY | 機場 | 西安咸陽國際機場 | OK：Xi'an / Xianyang Intl | [西安咸阳国际机场](https://zh.wikipedia.org/wiki/西安咸阳国际机场) OK | 2026-10-26 |
| 59 | KMG | 機場 | 昆明長水國際機場 | OK：Kunming / Changshui Intl | [昆明长水国际机场](https://zh.wikipedia.org/wiki/昆明长水国际机场) OK | 2026-10-26 |
| 60 | WUH | 機場 | 武漢天河國際機場 | OK：Wuhan / Tianhe Intl | [武汉天河国际机场](https://zh.wikipedia.org/wiki/武汉天河国际机场) OK | 2026-10-26 |
| 61 | TAO | 機場 | 青島膠東國際機場 | OK：Qingdao / Jiaodong International | [青岛胶东国际机场](https://zh.wikipedia.org/wiki/青岛胶东国际机场) OK | 2026-10-26 |
| 62 | CSX | 機場 | 長沙黃花國際機場 | OK：Changsha / Huanghua International | [长沙黄花国际机场](https://zh.wikipedia.org/wiki/长沙黄花国际机场) OK | 2026-10-26 |
| 63 | TSN | 機場 | 天津濱海國際機場 | OK：Tianjin / Binhai Intl | [天津滨海国际机场](https://zh.wikipedia.org/wiki/天津滨海国际机场) OK | 2026-10-26 |
| 64 | DLC | 機場 | 大連周水子國際機場 | OK：Dalian / Zhoushuizi Intl | [大连周水子国际机场](https://zh.wikipedia.org/wiki/大连周水子国际机场) OK | 2026-10-26 |
| 65 | SYX | 機場 | 三亞鳳凰國際機場 | OK：Sanya / Phoenix Intl | [三亚凤凰国际机场](https://zh.wikipedia.org/wiki/三亚凤凰国际机场) OK | 2026-10-26 |
| 66 | BKK | 機場 | 曼谷蘇凡納布機場 | OK：Bangkok / Suvarnabhumi Int'l；Bangkok / Metropolitan Area | [蘇凡納布機場](https://zh.wikipedia.org/wiki/蘇凡納布機場) OK | 2026-10-26 |
| 67 | DMK | 機場 | 曼谷廊曼國際機場 | OK：Bangkok / Don Mueang Int'l | [廊曼國際機場](https://zh.wikipedia.org/wiki/廊曼國際機場) OK | 2026-10-26 |
| 68 | CNX | 機場 | 清邁國際機場 | OK：Chiang Mai / Chiang Mai Intl. | [清邁國際機場](https://zh.wikipedia.org/wiki/清邁國際機場) OK | 2026-10-26 |
| 69 | HKT | 機場 | 普吉國際機場 | OK：Phuket / Phuket Intl. | [布吉國際機場](https://zh.wikipedia.org/wiki/布吉國際機場) OK | 2026-10-26 |
| 70 | SIN | 機場 | 新加坡樟宜機場 | OK：Singapore / Changi；Singapore / Metropolitan Area | [新加坡樟宜机场](https://zh.wikipedia.org/wiki/新加坡樟宜机场) OK | 2026-10-26 |
| 71 | KUL | 機場 | 吉隆坡國際機場 | OK：Kuala Lumpur / Metropolitan Area；Kuala Lumpur / Kuala Lumpur Intl. | [吉隆坡国际机场](https://zh.wikipedia.org/wiki/吉隆坡国际机场) OK | 2026-10-26 |
| 72 | PEN | 機場 | 檳城國際機場 | OK：Penang / Penang Intl. | [檳城國際機場](https://zh.wikipedia.org/wiki/檳城國際機場) OK | 2026-10-26 |
| 73 | BKI | 機場 | 亞庇國際機場 | OK：Kota Kinabalu / Kota Kinabalu Intl. | [亞庇國際機場](https://zh.wikipedia.org/wiki/亞庇國際機場) OK | 2026-10-26 |
| 74 | MNL | 機場 | 馬尼拉尼諾伊艾奎諾國際機場 | OK：Manila / Metropolitan Area；Manila / Ninoy Aquino Intl | [尼诺伊·阿基诺国际机场](https://zh.wikipedia.org/wiki/尼诺伊·阿基诺国际机场) OK | 2026-10-26 |
| 75 | CEB | 機場 | 麥克坦宿霧國際機場 | OK：Cebu / Mactan International | [麥克坦-宿霧國際機場](https://zh.wikipedia.org/wiki/麥克坦-宿霧國際機場) OK | 2026-10-26 |
| 76 | CRK | 機場 | 克拉克國際機場 | OK：Angeles/Mabalacat / Clark Intl | [克拉克国际机场](https://zh.wikipedia.org/wiki/克拉克国际机场) OK | 2026-10-26 |
| 77 | SGN | 機場 | 胡志明市新山一國際機場 | OK：Ho Chi Minh City / Tan Son Nhat Intl | [新山一空軍基地](https://zh.wikipedia.org/wiki/新山一空軍基地) OK | 2026-10-26 |
| 78 | HAN | 機場 | 河內內排國際機場 | OK：Hanoi / Noi Bai Intl | [內排國際機場](https://zh.wikipedia.org/wiki/內排國際機場) OK | 2026-10-26 |
| 79 | DAD | 機場 | 峴港國際機場 | OK：Da Nang / Da Nang Intl. | [峴港國際機場](https://zh.wikipedia.org/wiki/峴港國際機場) OK | 2026-10-26 |
| 80 | CXR | 機場 | 芽莊金蘭國際機場 | OK：Nha Trang / Cam Ranh Intl | [金蘭國際機場](https://zh.wikipedia.org/wiki/金蘭國際機場) OK | 2026-10-26 |
| 81 | CGK | 機場 | 雅加達蘇加諾-哈達國際機場 | OK：Jakarta / Soekarno-Hatta Intl | [蘇加諾-哈達國際機場](https://zh.wikipedia.org/wiki/蘇加諾-哈達國際機場) OK | 2026-10-26 |
| 82 | DPS | 機場 | 峇里島伍拉賴國際機場 | OK：Denpasar-Bali / Ngurah Rai | [伍拉·賴國際機場](https://zh.wikipedia.org/wiki/伍拉·賴國際機場) OK | 2026-10-26 |
| 83 | SYD | 機場 | 雪梨金斯福德史密斯機場 | OK：Sydney / Kingsford Smith；Sydney / Metropolitan Area | [悉尼機場](https://zh.wikipedia.org/wiki/悉尼機場) OK | 2026-10-26 |
| 84 | MEL | 機場 | 墨爾本機場 | OK：Melbourne / Melbourne Airport；Melbourne / Metropolitan Area | [墨爾本機場](https://zh.wikipedia.org/wiki/墨爾本機場) OK | 2026-10-26 |
| 85 | BNE | 機場 | 布里斯本機場 | OK：Brisbane / Brisbane Intl. | [布里斯班機場](https://zh.wikipedia.org/wiki/布里斯班機場) OK | 2026-10-26 |
| 86 | AKL | 機場 | 奧克蘭機場 | OK：Auckland / Auckland Intl.；Auckland / Metropolitan Area | [奧克蘭機場](https://zh.wikipedia.org/wiki/奧克蘭機場) OK | 2026-10-26 |
| 87 | GUM | 機場 | 關島國際機場 | OK：Guam / A.B. Won Pat Intl；Guam / Metropolitan Area | [安東尼奧·汪帕特國際機場](https://zh.wikipedia.org/wiki/安東尼奧·汪帕特國際機場) OK | 2026-10-26 |
| 88 | NYC | 城市 | 紐約 | OK：New York / Metropolitan Area | —（城市碼；另對照英文維基 IATA 代碼列表 metropolitan area 註記） | 2026-10-26 |
| 89 | JFK | 機場 | 紐約甘迺迪國際機場 | OK：New York / John F Kennedy Intl | [約翰·甘迺迪國際機場](https://zh.wikipedia.org/wiki/約翰·甘迺迪國際機場) OK | 2026-10-26 |
| 90 | EWR | 機場 | 紐華克自由國際機場 | OK：New York / Newark Liberty Intl | [紐華克自由國際機場](https://zh.wikipedia.org/wiki/紐華克自由國際機場) OK | 2026-10-26 |
| 91 | LGA | 機場 | 紐約拉瓜迪亞機場 | OK：New York / LaGuardia | [拉瓜地亞機場](https://zh.wikipedia.org/wiki/拉瓜地亞機場) OK | 2026-10-26 |
| 92 | LAX | 機場 | 洛杉磯國際機場 | OK：Los Angeles / Metropolitan Area；Los Angeles / Los Angeles Intl. | [洛杉磯國際機場](https://zh.wikipedia.org/wiki/洛杉磯國際機場) OK | 2026-10-26 |
| 93 | SFO | 機場 | 舊金山國際機場 | OK：San Francisco / San Francisco Intl. | [舊金山國際機場](https://zh.wikipedia.org/wiki/舊金山國際機場) OK | 2026-10-26 |
| 94 | SEA | 機場 | 西雅圖塔科馬國際機場 | OK：Seattle / Seattle-Tacoma Intl；Seattle / Metropolitan Area | [西雅圖-塔科馬國際機場](https://zh.wikipedia.org/wiki/西雅圖-塔科馬國際機場) OK | 2026-10-26 |
| 95 | ONT | 機場 | 加州安大略國際機場 | OK：Los Angeles / Ontario International | [安大略国际机场](https://zh.wikipedia.org/wiki/安大略国际机场) OK | 2026-10-26 |
| 96 | ORD | 機場 | 芝加哥歐海爾國際機場 | OK：Chicago / O'Hare International | [芝加哥奥黑尔国际机场](https://zh.wikipedia.org/wiki/芝加哥奥黑尔国际机场) OK | 2026-10-26 |
| 97 | IAH | 機場 | 休士頓喬治布希洲際機場 | OK：Houston / George Bush Intercont. | [喬治·布殊洲際機場](https://zh.wikipedia.org/wiki/喬治·布殊洲際機場) OK（人工確認） | 2026-10-26 |
| 98 | DFW | 機場 | 達拉斯沃斯堡國際機場 | OK：Dallas / Metropolitan Area；Fort Worth / Dallas/Ft Worth Intl；Dallas / Dallas/Ft Worth Intl | [达拉斯/沃思堡国际机场](https://zh.wikipedia.org/wiki/达拉斯/沃思堡国际机场) OK | 2026-10-26 |
| 99 | IAD | 機場 | 華盛頓杜勒斯國際機場 | OK：Washington / Dulles Intl | [华盛顿杜勒斯国际机场](https://zh.wikipedia.org/wiki/华盛顿杜勒斯国际机场) OK | 2026-10-26 |
| 100 | BOS | 機場 | 波士頓羅根國際機場 | OK：Boston / Edward L. Logan Intl；Boston / Metropolitan Area | [爱德华·劳伦斯·洛根将军国际机场](https://zh.wikipedia.org/wiki/爱德华·劳伦斯·洛根将军国际机场) OK | 2026-10-26 |
| 101 | PHX | 機場 | 鳳凰城天港國際機場 | OK：Phoenix / Sky Harbor Intl；Phoenix / Metropolitan Area | [鳳凰城天港國際機場](https://zh.wikipedia.org/wiki/鳳凰城天港國際機場) OK | 2026-10-26 |
| 102 | HNL | 機場 | 檀香山丹尼爾井上國際機場 | OK：Honolulu / Daniel K. Inouye Intl | [丹尼爾·K·井上國際機場](https://zh.wikipedia.org/wiki/丹尼爾·K·井上國際機場) OK | 2026-10-26 |
| 103 | YVR | 機場 | 溫哥華國際機場 | OK：Vancouver / Metropolitan Area；Vancouver / Vancouver Intl. | [溫哥華國際機場](https://zh.wikipedia.org/wiki/溫哥華國際機場) OK | 2026-10-26 |
| 104 | YYZ | 機場 | 多倫多皮爾遜國際機場 | OK：Toronto / Lester B. Pearson Intl | [多倫多皮爾遜國際機場](https://zh.wikipedia.org/wiki/多倫多皮爾遜國際機場) OK | 2026-10-26 |
| 105 | LON | 城市 | 倫敦 | OK：London / Metropolitan Area | —（城市碼；另對照英文維基 IATA 代碼列表 metropolitan area 註記） | 2026-10-26 |
| 106 | LHR | 機場 | 倫敦希斯洛機場 | OK：London / Heathrow | [希斯路機場](https://zh.wikipedia.org/wiki/希斯路機場) OK | 2026-10-26 |
| 107 | LGW | 機場 | 倫敦蓋威克機場 | OK：London / Gatwick | [蓋特威克機場](https://zh.wikipedia.org/wiki/蓋特威克機場) OK | 2026-10-26 |
| 108 | PAR | 城市 | 巴黎 | OK：Paris / Metropolitan Area | —（城市碼；另對照英文維基 IATA 代碼列表 metropolitan area 註記） | 2026-10-26 |
| 109 | CDG | 機場 | 巴黎戴高樂機場 | OK：Paris / Charles de Gaulle | [巴黎夏尔·戴高乐机场](https://zh.wikipedia.org/wiki/巴黎夏尔·戴高乐机场) OK | 2026-10-26 |
| 110 | ORY | 機場 | 巴黎奧利機場 | OK：Paris / Orly | [巴黎-奥利机场](https://zh.wikipedia.org/wiki/巴黎-奥利机场) OK | 2026-10-26 |
| 111 | AMS | 機場 | 阿姆斯特丹史基浦機場 | OK：Amsterdam / Schiphol Airport | [阿姆斯特丹史基浦機場](https://zh.wikipedia.org/wiki/阿姆斯特丹史基浦機場) OK | 2026-10-26 |
| 112 | FRA | 機場 | 法蘭克福機場 | OK：Frankfurt / Frankfurt Intl.；Frankfurt / Metropolitan Area | [法兰克福机场](https://zh.wikipedia.org/wiki/法兰克福机场) OK | 2026-10-26 |
| 113 | MUC | 機場 | 慕尼黑機場 | OK：Munich / Metropolitan Area；Munich / Munich Intl. | [慕尼黑机场](https://zh.wikipedia.org/wiki/慕尼黑机场) OK | 2026-10-26 |
| 114 | VIE | 機場 | 維也納國際機場 | OK：Vienna / Schwechat Intl | [維也納國際機場](https://zh.wikipedia.org/wiki/維也納國際機場) OK | 2026-10-26 |
| 115 | PRG | 機場 | 布拉格哈維爾國際機場 | OK：Prague / Vaclav Havel；Prague / Metropolitan Area | [布拉格瓦茨拉夫·哈維爾機場](https://zh.wikipedia.org/wiki/布拉格瓦茨拉夫·哈維爾機場) OK | 2026-10-26 |
| 116 | FCO | 機場 | 羅馬菲烏米奇諾機場 | OK：Rome / Fiumicino | [羅馬-菲烏米奇諾機場](https://zh.wikipedia.org/wiki/羅馬-菲烏米奇諾機場) OK | 2026-10-26 |
| 117 | MXP | 機場 | 米蘭馬爾彭薩機場 | OK：Milan / Malpensa | [米蘭-馬爾彭薩機場](https://zh.wikipedia.org/wiki/米蘭-馬爾彭薩機場) OK | 2026-10-26 |
| 118 | ZRH | 機場 | 蘇黎世機場 | OK：Zurich / Zurich Airport | [蘇黎世機場](https://zh.wikipedia.org/wiki/蘇黎世機場) OK | 2026-10-26 |
| 119 | MAD | 機場 | 馬德里巴拉哈斯機場 | OK：Madrid / Adolfo Suarez-Barajas；Madrid / Metropolitan Area | [阿道弗·苏亚雷斯马德里-巴拉哈斯机场](https://zh.wikipedia.org/wiki/阿道弗·苏亚雷斯马德里-巴拉哈斯机场) OK | 2026-10-26 |
| 120 | BCN | 機場 | 巴塞隆納埃爾普拉特機場 | OK：Barcelona / Josep Tarradellas Barcelona - El Prat | [何塞普·塔拉德利亚斯巴塞罗那-埃尔普拉特机场](https://zh.wikipedia.org/wiki/何塞普·塔拉德利亚斯巴塞罗那-埃尔普拉特机场) OK | 2026-10-26 |
| 121 | IST | 機場 | 伊斯坦堡機場 | OK：Istanbul / Istanbul Airport；Istanbul / Metropolitan Area | [伊斯坦堡機場](https://zh.wikipedia.org/wiki/伊斯坦堡機場) OK | 2026-10-26 |
| 122 | DXB | 機場 | 杜拜國際機場 | OK：Dubai / Dubai Intl.；Dubai / Metropolitan Area | [迪拜国际机场](https://zh.wikipedia.org/wiki/迪拜国际机场) OK | 2026-10-26 |
- 2026-10-26 dev-lead、frontend-engineer → qa-reviewer：第一批交件（對照表 122 筆、端點、驗證、combobox）；qa-reviewer NEEDS_CHANGES（high：未選取送出被默改 TPE；4 medium）→ 第二批修畢 → 複審 **PASS**（殘留 1 medium 由總經理順手補：input 事件 abort 飛行中請求）。
- 2026-10-26 總經理代跑 e2e（內建瀏覽器）：打「東」「大阪」下拉正確、鍵盤選取、Enter 不送表單、建立後列表與詳情顯示「台北桃園 TPE → 東京成田 NRT」、375px 下拉寬 310px 無溢出、選項 44px、未選取送出顯示「找不到此機場或城市，請從下拉選取」；API 對 ZZZ／LON／NRT→TYO 回 422。未驗：IME 組字、讀屏器。狀態 → done，待 CEO 驗收。
