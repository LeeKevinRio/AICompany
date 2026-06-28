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
        name: '麻將記分',
        short_name: '麻將記分',
        description: '台灣麻將 16 張 記分工具',
        theme_color: '#1f6f43',
        background_color: '#0f1410',
        display: 'standalone',
      },
    }),
  ],
  test: {
    globals: true,
    environment: 'node',
  },
});
