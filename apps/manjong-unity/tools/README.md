# tools

## render_tiles.py — 台灣麻將牌面圖（白色牌身）

產生 `client/Assets/Resources/Tiles/<牌碼>.png`（150×200，含牌身、圓角、陰影）與 `back.png`。
牌碼：`1m–9m`、`1p–9p`、`1s–9s`、`E S W N`、`RD GD WD`、`F1–F8`（春夏秋冬梅蘭竹菊）。

### 風格依據
參考台灣機打麻將牌的常見樣式（只當風格參考，未裁切、未描圖，所有圖形皆由程式重新繪製）：

- 牌身：白色瓷面 + 淡玉色牌厚，圓角。
- 萬子：上方黑色國字數字（5 用「伍」），下方紅色「萬」。
- 筒子：圓內有外圈與四瓣十字分格；配色 深綠 / 紅 / 近黑；1 筒為大圓（綠外圈、點狀花邊、紅色花心）。
- 條子：竹節以「串珠」畫成；5 條中間紅、7 條上方紅、9 條中間一列紅；8 條維持 M 字（上 M 下倒 M）；1 條為紅色小鳥配綠色尾羽。
- 字牌：中＝紅、發＝綠、東南西北＝黑；白板為黑色雙層裝飾框（框帶有梯狀鏤空）。
- 花牌：照另一張實物照片重新繪製的線稿風。春夏秋冬為左上黑色數字、右上紅色字；梅蘭竹菊為左上黑色字、右上紅色數字
  （數字刻意依伺服器正花規則：梅1 蘭2 竹3 菊4，與照片的菊3 竹4 不同，不要改，否則正花配對會錯）。花朵是紅色外框、內部白色，莖葉是綠色細線或描邊葉片。

### 花牌插圖做法
全部用 PIL 幾何繪製，沒有外部圖檔、沒有裁切照片：`bezier()` 曲線、`stroke()` 畫線、`oleaf()` 畫描邊葉片、
`ocircle()` 畫紅色外框圓（疊層花瓣）、`scallop_flower()` 畫波浪外緣的梅花。
各牌的函式為 `draw_peony / draw_lotus / draw_maple / draw_pine / draw_plum / draw_orchid / draw_bamboo /
draw_chrysanthemum`，座標用 0–1 的相對值；描邊寬度常數 `LW`、`GW` 以「縮到 33×44 仍可辨識」為準，檢查請看 44 px 高的縮圖總覽。

### 執行
```bash
pip install pillow
# 字型（不進 repo；放在與腳本同一個資料夾，或用 TILE_FONT_DIR 指到別處）
curl -LO https://raw.githubusercontent.com/notofonts/noto-cjk/main/Serif/SubsetOTF/TC/NotoSerifTC-Black.otf
curl -LO https://raw.githubusercontent.com/notofonts/noto-cjk/main/Serif/SubsetOTF/TC/NotoSerifTC-Bold.otf
python render_tiles.py ../client/Assets/Resources/Tiles
# 要看總覽圖：第二個參數指定輸出資料夾（原尺寸、92 px、44 px 高三張），不會寫進專案
python render_tiles.py ../client/Assets/Resources/Tiles /tmp/tile_sheets
```

配色與版面集中在腳本開頭的常數（RED / GREEN / INK）與各 `draw_*` 函式；
字型為 Noto Serif TC（SIL OFL 1.1，授權檔在 `Resources/Tiles/LICENSE-NotoSerifTC.txt`）。

## render_table.py — 牌桌貼圖（絨布、木桌框、控制台）

產生 `client/Assets/Resources/Table/` 的四張貼圖，全部用 PIL 程式繪製，不用網路圖片、不需要額外字型：

| 檔案 | 尺寸 | 內容 |
| --- | --- | --- |
| `felt.png` | 256×256 | 無縫綠色絨布小塊（織紋 + 纖維雜訊 + 雲狀濃淡），uGUI 用 `Image.Type.Tiled` 平鋪 |
| `felt_shade.png` | 388×369 | 暗角加中央柔光（RGBA 漸層），拉伸蓋在絨布上 |
| `frame.png` | 932×894 | 木桌框：胡桃木、四角斜接、木紋沿各邊方向、亮／暗斜邊、黃銅嵌線與銅釘；開口透明，外側落影與內側落影已燒進圖裡 |
| `console.png` | 248×210 | 桌心控制台（208×170，與一列牌河等寬）：深色外殼、黃銅細邊、三塊凹陷螢幕（資訊 / 羅盤 / 提示） |

```bash
pip install pillow
python render_table.py ../client/Assets/Resources/Table
# 另外輸出一般中盤與最壞情況（一般中盤：10 張牌河、1 組碰、13 張暗牌；最壞：30 張牌河、5 組槓、8 花）的示意圖，16:9 與 16:10（檔名加 _1610）各一張：<png 不含副檔名>_mid.png / _worst.png
# 無論有沒有 --preview，每次都會檢查每家 60 種狀態（牌河 12~31 張 × 0~5 組碰槓，牌列跟著牌河往外移）下、每一對座位有無牌重疊、超出絨布或蓋到控制台，並印出結果
python render_table.py ../client/Assets/Resources/Table --preview /tmp/table_layout.png --tiles ../client/Assets/Resources/Tiles
```

約 8 秒跑完；結果是決定性的（固定亂數種子），重跑會得到一樣的圖。幾何常數（框外尺寸 836×798、木框寬 30、絨布可見區、控制台 208×170 與三塊螢幕的矩形）在腳本開頭，
**必須與 `Assets/Scripts/Screens/TableScreen.cs` 的 `Table*` / `Console*` 常數一致**；顏色集中在 `FELT_*`、`WALNUT_*`、`BRASS*`。
絨布亮度刻意壓暗（最亮約 rgb(50,118,81)），讓牌河的高亮框（`Palette.FeltLastDiscardRing` / `FeltSameKindRing`）對它有 3:1 以上的對比；改絨布顏色時要重算。
匯入設定由 `Assets/Editor/ManjongTileImporter.cs` 套用（`felt.png` Wrap = Repeat、全部不壓縮）。
