"use client";

import { SkeletonBlock } from "../components/SkeletonBlock";
import { LIST_ARIA_LABEL } from "../lib/inventoryWording";
import { useDirectoryNames } from "../lib/queries";
import type { Position } from "../lib/types";
import { InventoryRow } from "./InventoryRow";
import { InventoryTableHeader } from "./InventoryRowView";

/**
 * Loading placeholder shaped like the loaded list so nothing jumps when data
 * arrives: header + three 64px rows from 1024px up, three 128px cards below.
 */
export function InventoryListSkeleton() {
  return (
    <div>
      <div className="hidden space-y-2 lg:block">
        <SkeletonBlock className="h-10 w-full" />
        <SkeletonBlock className="h-16 w-full" />
        <SkeletonBlock className="h-16 w-full" />
        <SkeletonBlock className="h-16 w-full" />
      </div>
      <div className="space-y-2 lg:hidden">
        <SkeletonBlock className="h-32 w-full" />
        <SkeletonBlock className="h-32 w-full" />
        <SkeletonBlock className="h-32 w-full" />
      </div>
    </div>
  );
}

/**
 * The inventory list: backend order (id ascending), every position, no
 * dependence on quotes or FX. Company names come from the directory; a miss
 * leaves the name line out.
 */
export function InventoryList({
  positions,
  highlightedId,
  pendingDeleteId,
  onRemove,
}: {
  positions: Position[];
  highlightedId: number | null;
  pendingDeleteId: number | null;
  onRemove: (position: Position) => void;
}) {
  const namesBySymbol = useDirectoryNames(positions.map((p) => p.symbol));
  return (
    <div role="table" aria-label={LIST_ARIA_LABEL} className="overflow-hidden rounded-md border border-neutral-800">
      <InventoryTableHeader />
      <div role="rowgroup">
        {positions.map((position) => (
          <InventoryRow
            key={position.id}
            position={position}
            name={namesBySymbol[position.symbol]}
            highlighted={highlightedId === position.id}
            pendingDeleteId={pendingDeleteId}
            onRemove={onRemove}
          />
        ))}
      </div>
    </div>
  );
}
