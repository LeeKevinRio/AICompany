export default function HomePage() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-12">
      <h1 className="text-3xl font-bold">stock-desk</h1>
      <p className="mt-2 text-neutral-400">
        把部位、市場訊號與風險上限放在同一畫面，輸出可解釋、可反駁、附失效條件的行動選項。
      </p>

      <section className="mt-8 rounded-lg border border-neutral-800 p-4">
        <h2 className="text-sm font-medium text-neutral-400">系統狀態</h2>
        <p className="mt-1 text-lg">後端狀態：尚未連線</p>
      </section>
    </main>
  );
}
