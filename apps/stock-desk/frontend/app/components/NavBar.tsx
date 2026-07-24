import Link from "next/link";

export function NavBar() {
  return (
    <header className="border-b border-neutral-800 px-4 py-3">
      <div className="mx-auto flex max-w-5xl items-center justify-between">
        <Link href="/" className="text-lg font-bold text-neutral-100">
          stock-desk
        </Link>
        <nav className="flex gap-4 text-sm text-neutral-400">
          <Link href="/" className="hover:text-neutral-100">
            總覽
          </Link>
          <Link href="/positions/import" className="hover:text-neutral-100">
            匯入 / 新增部位
          </Link>
        </nav>
      </div>
    </header>
  );
}
