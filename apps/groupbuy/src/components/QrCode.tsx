// QR code 顯示元件。
// 方案選擇：用 qrcode-generator（Kazuhiko Arase，MIT，zero runtime deps、自帶 .d.ts、~40KB）
// 純前端產生 QR 的 SVG，不打任何後端 / 第三方 API（買家連結不外流、離線可用）。
// 這符合企劃「純前端小套件或 canvas 自繪，避免重依賴」的方向——選小套件而非手刻 QR 編碼器，
// 因為 QR 的 Reed-Solomon 糾錯自刻風險高、不值得為 MVP 冒錯碼風險。
import { useMemo } from 'react';
import qrcode from 'qrcode-generator';

interface QrCodeProps {
  /** 要編進 QR 的文字（通常是分享連結）。 */
  value: string;
  /** 每個模組的像素邊長，預設 4。 */
  cellSize?: number;
}

export function QrCode({ value, cellSize = 4 }: QrCodeProps) {
  // 產生 SVG 字串（type 0 = 自動選版本；EC 'M' 中等糾錯，兼顧容量與掃描容錯）。
  const svg = useMemo(() => {
    try {
      const qr = qrcode(0, 'M');
      qr.addData(value);
      qr.make();
      return qr.createSvgTag({ cellSize, margin: 2, scalable: true });
    } catch {
      // 資料過長超出 QR 最大容量（type 40）等情況：回傳 null，改顯示 fallback 文字。
      return null;
    }
  }, [value, cellSize]);

  if (!svg) {
    return (
      <p className="muted" style={{ textAlign: 'center' }}>
        連結過長無法產生 QR，請直接複製連結分享。
      </p>
    );
  }

  return (
    <div
      className="qr-box"
      aria-label="填單連結 QR code"
      // 內容來自本地 qrcode-generator 產生的純 SVG（無使用者輸入注入風險）。
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
