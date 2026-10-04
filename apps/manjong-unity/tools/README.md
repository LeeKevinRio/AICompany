# tools

## render_tiles.py — 傳統麻將牌面圖

產生 `client/Assets/Resources/Tiles/<牌碼>.png`（150×200，含牌身、圓角、陰影）與 `back.png`。
筒子、條子、1 條孔雀、白板框線都是程式繪製；萬子數字、字牌、花牌用 Noto Serif TC（SIL OFL 1.1）。

```bash
pip install pillow
# 字型（不進 repo）：放在與腳本同一個資料夾
curl -LO https://raw.githubusercontent.com/notofonts/noto-cjk/main/Serif/SubsetOTF/TC/NotoSerifTC-Black.otf
curl -LO https://raw.githubusercontent.com/notofonts/noto-cjk/main/Serif/SubsetOTF/TC/NotoSerifTC-Bold.otf
python render_tiles.py ../client/Assets/Resources/Tiles
rm ../client/Assets/Resources/Tiles/_sheet.png   # 檢查用的總覽圖，不需要進專案
```

配色與版面集中在腳本開頭的常數（RED / GREEN / BLUE / NAVY、各點數的 layouts）。
