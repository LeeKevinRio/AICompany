// 把 useSessions 的回傳值透過 Context 提供給所有路由頁，避免逐層 props 傳遞。
import { createContext, useContext } from 'react';
import type { ReactNode } from 'react';
import { useSessions } from './hooks/useSessions';

type AppDataValue = ReturnType<typeof useSessions>;

const AppDataContext = createContext<AppDataValue | null>(null);

export function AppDataProvider({
  value,
  children,
}: {
  value: AppDataValue;
  children: ReactNode;
}) {
  return <AppDataContext.Provider value={value}>{children}</AppDataContext.Provider>;
}

export function useAppData(): AppDataValue {
  const ctx = useContext(AppDataContext);
  if (!ctx) throw new Error('useAppData 必須在 AppDataProvider 內使用');
  return ctx;
}
