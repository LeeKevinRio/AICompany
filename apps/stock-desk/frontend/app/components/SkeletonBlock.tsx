export function SkeletonBlock({ className = "" }: { className?: string }) {
  return (
    <div
      role="presentation"
      aria-hidden="true"
      className={`animate-pulse rounded bg-neutral-800 ${className}`}
    />
  );
}

export function SummaryCardsSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <SkeletonBlock className="h-24" />
      <SkeletonBlock className="h-24" />
      <SkeletonBlock className="h-20" />
      <SkeletonBlock className="h-20" />
    </div>
  );
}

export function TableSkeleton() {
  return (
    <div className="space-y-2">
      <SkeletonBlock className="h-10 w-full" />
      <SkeletonBlock className="h-10 w-full" />
      <SkeletonBlock className="h-10 w-full" />
      <SkeletonBlock className="h-10 w-full" />
    </div>
  );
}
