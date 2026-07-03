// 玩家頭像 PNG 清單（規範 5-2）。
// CEO 定案：直接使用現有 9 個 PNG（avatar_1~9），不採 brief 的方案 A(8)/B(11)。
// 檔案部署於 apps/web/public/avatars/，Vite 以 /avatars/avatar_N.png 靜態路徑取用。
// 未來要增減頭像只需改這個陣列，其他程式（選擇器、PlayerAvatar）無需更動。
export const PNG_AVATARS = [
  '/avatars/avatar_1.png',
  '/avatars/avatar_2.png',
  '/avatars/avatar_3.png',
  '/avatars/avatar_4.png',
  '/avatars/avatar_5.png',
  '/avatars/avatar_6.png',
  '/avatars/avatar_7.png',
  '/avatars/avatar_8.png',
  '/avatars/avatar_9.png',
] as const;
