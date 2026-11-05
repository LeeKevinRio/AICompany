/**
 * The same-row notes of one ledger row or snapshot batch, in the fixed order of
 * art spec 2026-11-04 section 7.1: N-188, N-189(D1), N-189(D2), then the W-B2L
 * family. Strings are returned verbatim: nothing is sorted, merged, re-worded
 * or split. A missing key (older backend), `null` and `""` are dropped, so an
 * empty result means "render no container".
 */
export interface RowNoteSource {
  //: W-B2L, W-B2LS (+ W-B2LSr, already composed in one string) or W-B2LSf.
  entry_before_exit_note?: string | null;
}

export function collectRowNotes(source: RowNoteSource): string[] {
  const ordered: (string | null | undefined)[] = [
    // N-188 slot: intentionally empty until that field exists.
    // N-189(D1) slot: intentionally empty until that field exists.
    // N-189(D2) slot: intentionally empty until that field exists.
    source.entry_before_exit_note,
  ];
  return ordered.filter((note): note is string => typeof note === "string" && note !== "");
}
