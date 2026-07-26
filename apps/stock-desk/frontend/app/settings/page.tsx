"use client";

import Link from "next/link";
import { ApiError } from "../lib/api";
import { useSettings } from "../lib/queries";
import { SkeletonBlock } from "../components/SkeletonBlock";
import { SettingsForm } from "./SettingsForm";
import { DataSourcesSection } from "./DataSourcesSection";
import { AlertRulesSection } from "./AlertRulesSection";

export default function SettingsPage() {
  const settings = useSettings(true);

  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-neutral-100">設定</h1>
        <Link href="/" className="text-sm text-sky-400 underline hover:text-sky-300">
          回總覽
        </Link>
      </div>

      <div className="mt-6 space-y-8">
        {settings.isPending && (
          <>
            <SkeletonBlock className="h-64 w-full" />
            <SkeletonBlock className="h-40 w-full" />
          </>
        )}
        {settings.isError && (
          <p role="alert" className="rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
            無法載入設定：{settings.error instanceof ApiError ? settings.error.message : "未知錯誤"}
          </p>
        )}
        {settings.isSuccess && (
          <>
            <SettingsForm settings={settings.data} />
            <DataSourcesSection />
          </>
        )}

        <AlertRulesSection />
      </div>
    </main>
  );
}
