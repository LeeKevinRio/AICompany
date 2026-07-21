// 商品圖片壓縮 / 大小估算。
// 純函式（computeScaledSize / estimateDataUrlBytes / estimateGroupsBytes）可單元測試；
// compressImageToDataUrl 是依賴 Image / canvas 的薄殼（瀏覽器端執行，不進單元測試）。

/** 壓縮參數：長邊縮到 512px、JPEG 品質 0.8。 */
export const IMAGE_MAX_EDGE = 512;
export const IMAGE_JPEG_QUALITY = 0.8;

/** 單張圖壓縮後上限 200KB，超過就拒絕。 */
export const IMAGE_MAX_BYTES = 200 * 1024;

/** localStorage 總量接近此值（4MB）就警示（多數瀏覽器上限約 5MB）。 */
export const STORAGE_WARN_BYTES = 4 * 1024 * 1024;

/**
 * 依「長邊不超過 maxEdge」等比計算縮放後尺寸；小於 maxEdge 不放大。
 * 純函式，方便測試。
 */
export function computeScaledSize(
  width: number,
  height: number,
  maxEdge: number = IMAGE_MAX_EDGE,
): { width: number; height: number } {
  if (!(width > 0) || !(height > 0)) return { width: 0, height: 0 };
  const longEdge = Math.max(width, height);
  if (longEdge <= maxEdge) return { width: Math.round(width), height: Math.round(height) };
  const scale = maxEdge / longEdge;
  return { width: Math.round(width * scale), height: Math.round(height * scale) };
}

/**
 * 概算一段 base64 data URL 的實際位元組數（僅算 base64 payload，忽略前綴標頭）。
 * 純函式，方便測試。
 */
export function estimateDataUrlBytes(dataUrl: string): number {
  if (typeof dataUrl !== 'string' || dataUrl.length === 0) return 0;
  const comma = dataUrl.indexOf(',');
  const b64 = comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl;
  if (b64.length === 0) return 0;
  const padding = b64.endsWith('==') ? 2 : b64.endsWith('=') ? 1 : 0;
  return Math.floor((b64.length * 3) / 4) - padding;
}

/**
 * 概算一組資料序列化後的位元組數（用 JSON 字串長度近似）。
 * 商品圖片為 ASCII base64、佔比最大，字元數 ≈ 位元組數，足以做「接近上限」的警示判斷。
 */
export function estimateGroupsBytes(value: unknown): number {
  try {
    return JSON.stringify(value)?.length ?? 0;
  } catch {
    return 0;
  }
}

/**
 * 把使用者選的圖片檔壓成 JPEG data URL（長邊 512px、品質 0.8）。
 * 薄殼：載入 Image → 畫到 canvas 縮放 → toDataURL。失敗 reject。
 * 不進單元測試（依賴瀏覽器 Image / canvas）；縮放與大小判斷的邏輯已抽成上面的純函式。
 */
export function compressImageToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      const { width, height } = computeScaledSize(img.naturalWidth, img.naturalHeight);
      if (width === 0 || height === 0) {
        reject(new Error('圖片尺寸無效'));
        return;
      }
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        reject(new Error('無法建立畫布'));
        return;
      }
      ctx.drawImage(img, 0, 0, width, height);
      try {
        resolve(canvas.toDataURL('image/jpeg', IMAGE_JPEG_QUALITY));
      } catch (err) {
        reject(err instanceof Error ? err : new Error('圖片壓縮失敗'));
      }
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('圖片讀取失敗（格式不支援？）'));
    };
    img.src = url;
  });
}
