import Link from "next/link";
import { EMPTY_ADD_LINK, EMPTY_TITLE, INVENTORY_ROUTE } from "../lib/inventoryWording";

/**
 * One-line empty state. The home page shows the 新增持倉 button (pointing at
 * the inventory page); the inventory page itself passes `withAddLink={false}`
 * because its add section is already expanded right below.
 */
export function EmptyPositionsState({ withAddLink = true }: { withAddLink?: boolean }) {
  return (
    <div className="rounded-lg border border-dashed border-neutral-800 p-6 text-center">
      <p className="text-lg font-medium text-neutral-100">{EMPTY_TITLE}</p>
      {withAddLink && (
        <Link
          href={INVENTORY_ROUTE}
          className="mt-4 inline-flex min-h-11 items-center rounded-md bg-neutral-100 px-4 text-sm font-medium text-neutral-900 hover:bg-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
        >
          {EMPTY_ADD_LINK}
        </Link>
      )}
    </div>
  );
}
