// 用 Context 把 useGroups 的資料與操作往下傳，避免逐頁 prop drilling。
import { createContext, useContext } from 'react';
import type { ReactNode } from 'react';
import type { GroupsApi } from './hooks/useGroups';

const AppDataContext = createContext<GroupsApi | null>(null);

export function AppDataProvider({
  value,
  children,
}: {
  value: GroupsApi;
  children: ReactNode;
}) {
  return <AppDataContext.Provider value={value}>{children}</AppDataContext.Provider>;
}

export function useAppData(): GroupsApi {
  const ctx = useContext(AppDataContext);
  if (!ctx) throw new Error('useAppData 必須在 AppDataProvider 內使用');
  return ctx;
}
