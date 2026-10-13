/**
 * A minimal parser for the markup `renderToStaticMarkup` produces, so render
 * tests can assert structure (next sibling, ancestors, class tokens) without a
 * DOM library: this project's vitest runs in plain Node with no jsdom.
 *
 * It understands exactly what React's static output contains -- well-formed
 * tags, double-quoted attributes, the `<!-- -->` separators between adjacent
 * text nodes, and the five entities React escapes -- and nothing else.
 */

export interface HtmlElement {
  tag: string;
  attrs: Record<string, string>;
  children: HtmlNode[];
  parent: HtmlElement | null;
}

export type HtmlNode = HtmlElement | string;

const VOID_TAGS = new Set(["col", "br", "hr", "img", "input", "meta", "link"]);

function decodeEntities(text: string): string {
  return text
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&");
}

function parseAttributes(source: string): Record<string, string> {
  const attrs: Record<string, string> = {};
  const pattern = /([^\s=/>]+)(?:="([^"]*)")?/g;
  for (const match of source.matchAll(pattern)) {
    const name = match[1];
    if (name === undefined) continue;
    attrs[name] = decodeEntities(match[2] ?? "");
  }
  return attrs;
}

export function parseHtml(html: string): HtmlElement {
  const root: HtmlElement = { tag: "#root", attrs: {}, children: [], parent: null };
  let current = root;
  const token = /<!--[\s\S]*?-->|<\/([A-Za-z0-9]+)>|<([A-Za-z0-9]+)((?:\s+[^\s>]+?(?:="[^"]*")?)*)\s*\/?>|([^<]+)/g;
  for (const match of html.matchAll(token)) {
    const [whole, closing, opening, attrSource, text] = match;
    if (whole.startsWith("<!--")) continue;
    if (closing !== undefined) {
      if (current.tag !== closing || current.parent === null) {
        throw new Error(`unbalanced </${closing}> inside <${current.tag}>`);
      }
      current = current.parent;
    } else if (opening !== undefined) {
      const element: HtmlElement = {
        tag: opening,
        attrs: parseAttributes(attrSource ?? ""),
        children: [],
        parent: current,
      };
      current.children.push(element);
      if (!VOID_TAGS.has(opening)) current = element;
    } else if (text !== undefined) {
      current.children.push(decodeEntities(text));
    }
  }
  if (current !== root) throw new Error(`unclosed <${current.tag}>`);
  return root;
}

export function elementsOf(node: HtmlElement): HtmlElement[] {
  const found: HtmlElement[] = [];
  for (const child of node.children) {
    if (typeof child === "string") continue;
    found.push(child, ...elementsOf(child));
  }
  return found;
}

export function textOf(node: HtmlNode): string {
  if (typeof node === "string") return node;
  return node.children.map(textOf).join("");
}

export function classTokens(node: HtmlElement): string[] {
  return (node.attrs.class ?? "").split(/\s+/).filter((token) => token !== "");
}

export function ancestorsOf(node: HtmlElement): HtmlElement[] {
  const chain: HtmlElement[] = [];
  for (let up = node.parent; up !== null; up = up.parent) chain.push(up);
  return chain;
}

export function findAll(root: HtmlElement, predicate: (element: HtmlElement) => boolean): HtmlElement[] {
  return elementsOf(root).filter(predicate);
}

/** The single element matching, or a thrown error naming how many matched. */
export function findOne(root: HtmlElement, predicate: (element: HtmlElement) => boolean, what: string): HtmlElement {
  const matches = findAll(root, predicate);
  if (matches.length !== 1) throw new Error(`expected exactly one ${what}, found ${matches.length}`);
  const [only] = matches;
  if (only === undefined) throw new Error(`expected exactly one ${what}`);
  return only;
}

/** Element children only, in document order. */
export function elementChildren(node: HtmlElement): HtmlElement[] {
  return node.children.filter((child): child is HtmlElement => typeof child !== "string");
}

export function nextElementSibling(node: HtmlElement): HtmlElement | null {
  if (node.parent === null) return null;
  const siblings = elementChildren(node.parent);
  const index = siblings.indexOf(node);
  return siblings[index + 1] ?? null;
}
