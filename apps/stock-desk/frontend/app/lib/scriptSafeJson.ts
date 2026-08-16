/**
 * Serializes a value to JSON safe for embedding as the literal text content
 * of an inline `<script>` element (`dangerouslySetInnerHTML`).
 *
 * Security fix (qa-reviewer NEEDS_CHANGES on 4938eb5, critical reflected
 * XSS, second of two independent layers — the first is the symbol whitelist
 * in `tradingViewSymbol.ts`): plain `JSON.stringify` output can still
 * contain the raw characters `<`, `>`, `&`, so a value containing e.g.
 * `</script>` would prematurely close the host `<script>` tag and let
 * whatever follows be parsed as HTML/script by the browser — independent of
 * whether the whitelist upstream is ever bypassed or a future call site
 * feeds this an unvalidated value directly. Escaping those three characters
 * to their `\uXXXX` form is valid inside a JSON string (the widget script
 * parses this as JSON, and `<` etc. decode back to the original
 * character before it ever reaches that parser) and cannot be used to break
 * out of the surrounding `<script>` element.
 */
export function toScriptSafeJson(value: unknown): string {
  return JSON.stringify(value)
    .replace(/</g, "\\u003c")
    .replace(/>/g, "\\u003e")
    .replace(/&/g, "\\u0026");
}
