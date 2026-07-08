/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

// Vite 設定：React + PWA。
// PWA 讓網頁可「加到主畫面」像 app 一樣使用，也是未來轉原生（Capacitor）的第一步。
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      // MVP 只用最小 manifest；正式圖示等之後再補。
      manifest: {
        name: 'MaJong — 台灣麻將記分',
        short_name: 'MaJong',
        description: '台灣麻將 16 張 記分工具',
        theme_color: '#1f6f43',
        background_color: '#0f1410',
        display: 'standalone',
      },
    }),
  ],
  // 確保整個依賴鏈（含 recharts 這種被 lazy 動態 import 的套件）都共用同一份
  // react / react-dom 實例，避免出現多份 React 造成 "Invalid hook call"
  // （recharts 內部 useRef 讀到 null）的錯誤。
  resolve: {
    dedupe: ['react', 'react-dom'],
  },
  // 把 recharts 及其 React 依賴鏈一起預打包，讓 dev 下 lazy import recharts 時
  // 不會另外觸發 dep optimization 產生與主 app 不同份的 React chunk。
  optimizeDeps: {
    include: ['recharts', 'react', 'react-dom', 'react-dom/client'],
  },
  test: {
    globals: true,
    environment: 'node',
  },
});
