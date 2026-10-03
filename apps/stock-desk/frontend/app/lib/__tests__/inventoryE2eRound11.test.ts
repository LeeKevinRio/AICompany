import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { InventoryRowView } from "../../positions/InventoryRowView";
import { decideComboboxKeyDown, shouldOpenAfterDebounce } from "../directorySearch";
import { fieldErrorAria, fieldErrorId } from "../fieldErrorA11y";
import { FOCUSABLE_SELECTOR, trapTabTarget } from "../focusTrap";
import type { Position } from "../types";

// Regression pins for qa-e2e round 11 (inventory page, four non-blocking defects).

function read(rel: string): string {
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf-8");
}

const position: Position = {
  id: 7,
  symbol: "2330",
  market: "TW",
  quantity: "1000",
  avg_cost: "605.5",
  currency: "TWD",
  opened_at: null,
  instrument_type: "stock",
  sector: null,
  note: "a very long note ".repeat(20),
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z",
};

describe("defect 1: mobile card note label keeps one line", () => {
  const html = renderToStaticMarkup(
    createElement(InventoryRowView, {
      position,
      name: "台積電",
      highlighted: false,
      mode: "display",
      draft: { quantity: position.quantity, avg_cost: position.avg_cost, note: position.note ?? "" },
      onDraftChange: () => {},
      saveError: null,
      saving: false,
      pendingDeleteId: null,
      onEdit: () => {},
      onSave: () => {},
      onCancel: () => {},
      onMore: () => {},
      onRemove: () => {},
    }),
  );

  it("the 備註 label span is shrink-0 and no-wrap", () => {
    const match = /<span class="([^"]*)">備註<\/span>/.exec(html);
    expect(match).not.toBeNull();
    const classes = (match?.[1] ?? "").split(" ");
    expect(classes).toContain("shrink-0");
    expect(classes).toContain("whitespace-nowrap");
    expect(classes).toContain("lg:hidden");
  });

  it("the note value stays shrinkable and wraps instead of overflowing", () => {
    expect(html).toMatch(/<span class="[^"]*\bmin-w-0\b[^"]*\bbreak-words\b[^"]*">a very long note/);
  });
});

describe("defect 2: add / edit form field errors are announced and linked", () => {
  it("fieldErrorAria links an erroring input to its alert line and marks it invalid", () => {
    expect(fieldErrorAria("quantity", "數量必須大於 0")).toEqual({
      "aria-invalid": true,
      "aria-describedby": "quantity-error",
    });
    expect(fieldErrorId("edit-note")).toBe("edit-note-error");
  });

  it("emits nothing while the field has no error", () => {
    expect(fieldErrorAria("quantity", undefined)).toEqual({});
    expect(fieldErrorAria("quantity", "")).toEqual({});
  });

  for (const [file, prefix] of [
    ["../../positions/ManualAddForm.tsx", ""],
    ["../../components/EditPositionModal.tsx", "edit-"],
  ] as const) {
    describe(file, () => {
      const source = read(file);

      it("the error line is role=alert with the id the input points at", () => {
        expect(source).toMatch(/<p id=\{fieldErrorId\(fieldId\)\} role="alert"/);
      });

      it("every field's error line has a matching aria wiring on its input", () => {
        const errorLines = [...source.matchAll(/<FieldError fieldId="([^"]+)"/g)].map((m) => m[1]);
        expect(errorLines).toEqual(
          ["symbol", "market", "instrument_type", "currency", "quantity", "avg_cost", "opened_at", "sector", "note"].map(
            (name) => `${prefix}${name}`,
          ),
        );
        for (const fieldId of errorLines) {
          expect(source).toContain(`id="${fieldId}"`);
          expect(source).toMatch(new RegExp(`fieldErrorAria\\("${fieldId}", fieldErrors\\.`));
        }
        expect(source).not.toMatch(/<FieldError message=/);
      });
    });
  }

  it("SymbolCombobox forwards aria-invalid / aria-describedby to its input", () => {
    const source = read("../../components/SymbolCombobox.tsx");
    expect(source).toContain("aria-invalid={ariaInvalid}");
    expect(source).toContain("aria-describedby={ariaDescribedBy}");
  });
});

describe("defect 3: edit dialog manages focus", () => {
  const source = read("../../components/EditPositionModal.tsx");

  it("moves focus to the first field on open", () => {
    expect(source).toMatch(/useEffect\(\(\) => \{\s*formRef\.current\?\.querySelector<HTMLElement>\(FIRST_FIELD_SELECTOR\)\?\.focus\(\);\s*\}, \[\]\);/);
    expect(source).toContain("ref={formRef}");
  });

  it("wires the Tab trap on the dialog element and keeps Esc to close", () => {
    expect(source).toContain("ref={dialogRef}");
    expect(source).toContain("onKeyDown={handleDialogKeyDown}");
    expect(source).toContain("trapTabTarget(");
    expect(source).toContain('event.key === "Escape" && !updateMutation.isPending');
  });

  it("Tab wraps last -> first and Shift+Tab wraps first -> last", () => {
    expect(trapTabTarget(5, 4, false)).toBe(0);
    expect(trapTabTarget(5, 0, true)).toBe(4);
  });

  it("leaves in-dialog movement to the browser", () => {
    expect(trapTabTarget(5, 2, false)).toBeNull();
    expect(trapTabTarget(5, 2, true)).toBeNull();
    expect(trapTabTarget(5, 0, false)).toBeNull();
    expect(trapTabTarget(5, 4, true)).toBeNull();
  });

  it("pulls focus back in when it is outside the dialog's focusable list", () => {
    expect(trapTabTarget(5, -1, false)).toBe(0);
    expect(trapTabTarget(5, -1, true)).toBe(4);
  });

  it("does nothing for a dialog without focusable elements", () => {
    expect(trapTabTarget(0, -1, false)).toBeNull();
  });

  it("the focusable selector skips disabled controls", () => {
    expect(FOCUSABLE_SELECTOR).toContain("button:not([disabled])");
    expect(FOCUSABLE_SELECTOR).toContain("input:not([disabled])");
  });

  it("the trigger-side focus restore stays in the caller", () => {
    const row = read("../../positions/InventoryRow.tsx");
    expect(row).toMatch(/function handleModalClose\(\) \{\s*pendingFocus\.current = "edit";/);
  });
});

describe("defect 4: directory dropdown does not outlive the input's focus", () => {
  const source = read("../../components/SymbolCombobox.tsx");

  it("a debounce that fires after a blur must not open the dropdown", () => {
    expect(shouldOpenAfterDebounce(false)).toBe(false);
    expect(shouldOpenAfterDebounce(true)).toBe(true);
  });

  it("tracks focus on focus / blur and guards the debounced open with it", () => {
    expect(source).toMatch(/onFocus=\{\(\) => \{\s*focusedRef\.current = true;/);
    expect(source).toMatch(/onBlur=\{\(\) => \{\s*focusedRef\.current = false;/);
    expect(source).toContain("if (shouldOpenAfterDebounce(focusedRef.current)) setOpen(true);");
    // The late open is the only unguarded `setOpen(true)` path left besides focus / arrow keys.
    expect(source).not.toMatch(/setDebouncedQuery\(trimmed\);\s*setOpen\(true\);/);
  });

  it("blur still closes an open dropdown, and Esc closes it", () => {
    expect(source).toMatch(/window\.setTimeout\(\(\) => closeDropdown\(\), \d+\)/);
    expect(decideComboboxKeyDown("Escape", { open: true, highlightedIndex: -1, candidatesLength: 0 })).toEqual({
      kind: "close",
    });
  });
});
