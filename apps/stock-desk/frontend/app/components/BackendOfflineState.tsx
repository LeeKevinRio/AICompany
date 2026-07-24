export function BackendOfflineState({ onRetry }: { onRetry: () => void }) {
  return (
    <div
      role="alert"
      className="mx-auto mt-16 max-w-md rounded-lg border border-neutral-800 bg-neutral-900/60 p-8 text-center"
    >
      <p className="text-lg font-semibold text-neutral-100">後端未連線</p>
      <p className="mt-2 text-sm text-neutral-400">
        無法連線到後端服務，請確認服務是否已啟動，或稍後再試一次。
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-6 rounded-md bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-900 hover:bg-white"
      >
        重試連線
      </button>
    </div>
  );
}
