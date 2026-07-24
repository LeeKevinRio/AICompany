import Link from "next/link";
import { ImportCsvSection } from "./ImportCsvSection";
import { ManualAddForm } from "./ManualAddForm";

export default function ImportPositionsPage() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-neutral-100">匯入 / 新增部位</h1>
        <Link href="/" className="text-sm text-sky-400 underline hover:text-sky-300">
          回總覽
        </Link>
      </div>
      <p className="mt-2 text-sm text-neutral-400">
        以 CSV 批次匯入既有部位，或逐筆手動新增。
      </p>

      <div className="mt-6 flex flex-col gap-6">
        <ImportCsvSection />
        <ManualAddForm />
      </div>
    </main>
  );
}
