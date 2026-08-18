/**
 * Splitting a post body into plain text and the cashtags inside it.
 *
 * The pattern mirrors `CASHTAG_RE` in `backend/app/services/community.py`, which is what decides
 * which tickers a post is filed under. Keep the two in step: a symbol the server indexes but this
 * misses would be filterable yet not clickable, and the reverse would offer a link to a filter that
 * returns nothing.
 */
const CASHTAG_RE = /\$([A-Za-z]{1,6}(?:[.-][A-Za-z]{1,4})?)\b/g;

export type BodySegment =
  | { kind: "text"; value: string }
  | { kind: "cashtag"; value: string; symbol: string };

/**
 * Break `body` into consecutive segments, each either plain text or a cashtag.
 *
 * Returned as data rather than markup so the caller decides what a ticker links to, and so this
 * stays testable without a DOM. `value` keeps the text exactly as typed (`$aapl` stays lowercase on
 * screen) while `symbol` is the uppercased form the API filters on.
 */
export function splitCashtags(body: string): BodySegment[] {
  const segments: BodySegment[] = [];
  let cursor = 0;

  // `matchAll` on a /g regex avoids the shared-lastIndex trap of calling .exec() in a loop.
  for (const match of body.matchAll(CASHTAG_RE)) {
    const start = match.index ?? 0;
    if (start > cursor) segments.push({ kind: "text", value: body.slice(cursor, start) });
    segments.push({ kind: "cashtag", value: match[0], symbol: match[1].toUpperCase() });
    cursor = start + match[0].length;
  }
  if (cursor < body.length) segments.push({ kind: "text", value: body.slice(cursor) });
  return segments;
}
