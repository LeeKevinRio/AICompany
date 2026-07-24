import Link from "next/link";

export function EmptyPositionsState() {
  return (
    <div className="rounded-lg border border-dashed border-neutral-800 p-10 text-center">
      <p className="text-lg font-medium text-neutral-100">目前尚無任何持倉</p>
      <p className="mt-2 text-sm text-neutral-400">
        匯入 CSV 檔案，或手動新增第一筆部位，開始追蹤損益。
      </p>
      <Link
        href="/positions/import"
        className="mt-6 inline-block rounded-md bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-900 hover:bg-white"
      >
        前往匯入 CSV
      </Link>
    </div>
  );
}
