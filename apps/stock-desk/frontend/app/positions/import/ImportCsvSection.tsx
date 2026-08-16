"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { positionsTemplateCsvUrl } from "../../lib/api";
import { ErrorPanel } from "../../components/ErrorPanel";
import { shouldBlockPositionSubmit, submitButtonState } from "../../lib/positionFormSubmit";
import { useImportPositionsCsv } from "../../lib/queries";

export function ImportCsvSection() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const importMutation = useImportPositionsCsv();
  const submitButton = submitButtonState(importMutation.isPending, "上傳並匯入", "匯入中…");

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Same re-entry guard as the other three submit surfaces (see
    // `positionFormSubmit.ts`'s doc comment) — the file input itself does
    // not implicitly submit on Enter, but the guard is kept here too so the
    // handler's own behaviour does not depend on that browser detail.
    if (shouldBlockPositionSubmit(importMutation.isPending)) return;
    if (!selectedFile) return;
    importMutation.mutate(selectedFile, {
      onSuccess: () => {
        setSelectedFile(null);
        if (fileInputRef.current) fileInputRef.current.value = "";
      },
    });
  }

  return (
    <section className="rounded-lg border border-neutral-800 p-5">
      <h2 className="text-lg font-semibold text-neutral-100">CSV 匯入</h2>
      <p className="mt-1 text-sm text-neutral-400">
        下載範本並依格式填寫後上傳，即可一次匯入多筆部位。
      </p>
      <a
        href={positionsTemplateCsvUrl}
        className="mt-3 inline-block text-sm text-sky-400 underline hover:text-sky-300"
      >
        下載 CSV 範本
      </a>

      <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,text/csv"
          aria-label="選擇 CSV 檔案"
          onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
          className="text-sm text-neutral-300 file:mr-3 file:rounded-md file:border-0 file:bg-neutral-800 file:px-3 file:py-2 file:text-sm file:text-neutral-100 hover:file:bg-neutral-700"
        />
        <button
          type="submit"
          disabled={!selectedFile || submitButton.disabled}
          className="rounded-md bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-900 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitButton.label}
        </button>
      </form>

      {importMutation.isError && (
        <div className="mt-4">
          <ErrorPanel label="匯入失敗" error={importMutation.error} />
        </div>
      )}

      {importMutation.isSuccess && (
        <div className="mt-4 space-y-3">
          <p role="status" className="rounded-md border border-emerald-900 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-300">
            成功匯入 {importMutation.data.imported} 筆。
            <Link href="/" className="ml-2 underline hover:text-emerald-200">
              回總覽查看
            </Link>
          </p>

          {importMutation.data.errors.length > 0 && (
            <div className="overflow-x-auto rounded-md border border-neutral-800">
              <table className="w-full min-w-[420px] text-left text-sm">
                <caption className="sr-only">匯入錯誤明細</caption>
                <thead className="bg-neutral-900 text-neutral-400">
                  <tr>
                    <th scope="col" className="px-3 py-2 font-medium">
                      列
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      欄位
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      原因
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {importMutation.data.errors.map((err, idx) => (
                    <tr key={`${err.row}-${err.field}-${idx}`} className="border-t border-neutral-800">
                      <td className="px-3 py-2 text-neutral-300">{err.row}</td>
                      <td className="px-3 py-2 text-neutral-300">{err.field}</td>
                      <td className="px-3 py-2 text-neutral-300">{err.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
