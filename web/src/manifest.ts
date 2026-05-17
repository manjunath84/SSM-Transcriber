// Minimal frontmatter splitter for transcript markdown.
//
// Splits a leading `---` fenced block of simple `key: value` lines from
// the body. Intentionally NOT a YAML parser: only top-level `key: value`
// lines between the leading fences are parsed (no nesting, lists, or
// quoting). Anything without a leading `---` fence is returned verbatim.

export interface SplitResult {
  frontmatter: Record<string, string>;
  body: string;
}

export function splitFrontmatter(md: string): SplitResult {
  if (!md.startsWith("---\n")) {
    return { frontmatter: {}, body: md };
  }
  const rest = md.slice(4);
  const end = rest.indexOf("\n---\n");
  const endBare = rest.endsWith("\n---") ? rest.length - 4 : -1;
  let fmText: string;
  let body: string;
  if (end !== -1) {
    fmText = rest.slice(0, end);
    body = rest.slice(end + 5);
  } else if (endBare !== -1) {
    fmText = rest.slice(0, endBare);
    body = "";
  } else {
    // No closing fence: not valid frontmatter, return verbatim.
    return { frontmatter: {}, body: md };
  }

  const frontmatter: Record<string, string> = {};
  for (const line of fmText.split("\n")) {
    if (!line.trim()) continue;
    const idx = line.indexOf(":");
    if (idx === -1) continue;
    const key = line.slice(0, idx).trim();
    const value = line.slice(idx + 1).trim();
    if (key) frontmatter[key] = value;
  }
  return { frontmatter, body };
}
