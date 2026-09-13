// Body-source profile v1. Keep in sync with contracts/src/lib/BodyParser.sol.
// HTML remains source text; we never treat decoded bytes as trusted DOM markup.
export const MAX_BODY = 196608;
export const MAX_WINDOW = 4096;
export function latin1Bytes(s: string): Uint8Array {
  return Uint8Array.from(s, c => c.charCodeAt(0) & 255);
}
export function bytesLatin1(b: Uint8Array): string {
  let out = "";
  for (let i = 0; i < b.length; i += 8192) out += String.fromCharCode(...b.subarray(i, i + 8192));
  return out;
}
export function canonicalizeBody(raw: string, mode: string): Uint8Array {
  let lines = raw.replace(/\r\n/g, "\n").split("\n");
  if (mode === "relaxed") lines = lines.map(l => l.replace(/[ \t]+/g, " ").replace(/ +$/, ""));
  else if (mode !== "simple") throw new Error("Unsupported DKIM body canonicalization");
  while (lines.length && lines[lines.length - 1] === "") lines.pop();
  // RFC 6376 relaxed empty-body hash is SHA256 of zero bytes; simple is CRLF.
  return latin1Bytes(lines.length ? lines.join("\r\n") + "\r\n" : mode === "simple" ? "\r\n" : "");
}
export function signedBodyEncoding(header: string): number {
  const fields = (name: string) => header.split("\r\n").filter(l => l.startsWith(name + ":")).map(l => l.slice(name.length + 1));
  const ct = fields("content-type");
  if (ct.length !== 1 || !/^text\/(plain|html)(?:\s*;|$)/i.test(ct[0])) throw new Error("Body profile supports signed, single-part text/plain or text/html only");
  const charsets = [...ct[0].matchAll(/;\s*charset\s*=\s*([^;]*)/gi)];
  if (charsets.length > 1 || charsets.some(m => !/^(?:utf-8|us-ascii|"utf-8"|"us-ascii")$/i.test(m[1].trim()))) throw new Error("Unsupported body charset");
  const enc = fields("content-transfer-encoding");
  if (enc.length > 1) throw new Error("Duplicate signed transfer encoding");
  if (!enc.length || enc[0].toLowerCase() === "quoted-printable") return 1;
  if (/^(?:7bit|8bit)$/i.test(enc[0])) return 0;
  throw new Error("Unsupported signed body encoding");
}
export function decodeBodyWindow(body: Uint8Array, start: number, length: number, encoding: number, bounded = true): Uint8Array {
  if (!Number.isSafeInteger(start) || !Number.isSafeInteger(length) || start < 0 || length <= 0 || (bounded && length > MAX_WINDOW) || start + length > body.length) throw new Error("Body window outside allowed bounds");
  if (encoding === 1 && ((start > 0 && body[start-1] === 61) || (start > 1 && body[start-2] === 61))) throw new Error("Window begins inside a quoted-printable escape");
  const out: number[] = [];
  for (let i = start; i < start + length; i++) {
    let c = body[i];
    if (encoding === 1 && c === 61) {
      if (i + 2 >= start + length) throw new Error("Window ends inside a quoted-printable escape");
      if (body[i+1] === 13 && body[i+2] === 10) { i += 2; continue; }
      const hex = String.fromCharCode(body[i+1],body[i+2]);
      if (!/^[0-9a-f]{2}$/i.test(hex)) throw new Error("Malformed quoted-printable body");
      c = parseInt(hex, 16); i += 2;
    }
    out.push(c);
  }
  return Uint8Array.from(out);
}
export function substringPattern(pattern: string): boolean {
  let escaped = false, inClass = false;
  for (const c of pattern) {
    if (escaped) { escaped = false; continue; }
    if (c === "\\") { escaped = true; continue; }
    if (c === "[") inClass = true;
    else if (c === "]") inClass = false;
    else if (!inClass && (c === "^" || c === "$")) return false;
  }
  return true;
}
export function bodyRegex(pattern: string): RegExp {
  return new RegExp(pattern.replace(/^\(\?i\)/, ""), pattern.startsWith("(?i)") ? "i" : "");
}
export function selectBodyWindow(body: Uint8Array, encoding: number, pattern = ""): { bodyOffset: bigint; bodyLength: bigint; bodyExcerpt: string } {
  if (body.length > MAX_BODY) throw new Error("Canonical body exceeds 192 KiB limit");
  if (!substringPattern(pattern)) throw new Error("Body rules must use substring patterns without ^ or $ anchors");
  const decoded = decodeBodyWindow(body, 0, body.length, encoding, false);
  const full = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(decoded);
  const match = bodyRegex(pattern).exec(full);
  if (!match) throw new Error("No match in decoded body source");
  const utf8 = new TextEncoder();
  const matchStart = utf8.encode(full.slice(0, match.index)).length;
  const matchEnd = matchStart + utf8.encode(match[0]).length;
  // Map decoded octets back to authenticated canonical-body offsets.
  const offsets: number[] = [];
  for (let i = 0; i < body.length; i++) {
    if (encoding === 1 && body[i] === 61) {
      if (body[i+1] === 13 && body[i+2] === 10) { i += 2; continue; }
      offsets.push(i); i += 2;
    } else offsets.push(i);
  }
  offsets.push(body.length);
  for (let margin = 0; margin >= 0; margin -= 16) {
    for (let expand = 0; expand < 12; expand++) {
      const begin = Math.max(0, matchStart - margin - expand);
      const finish = Math.min(decoded.length, matchEnd + margin + expand);
      const start = offsets[begin], length = offsets[finish] - start;
      if (length > MAX_WINDOW || length <= 0) continue;
      try {
        const excerpt = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(decodeBodyWindow(body, start, length, encoding));
        if (bodyRegex(pattern).test(excerpt)) return { bodyOffset: BigInt(start), bodyLength: BigInt(length), bodyExcerpt: excerpt };
      } catch { /* expand to a safe encoded/UTF-8 boundary */ }
    }
  }
  throw new Error("Matching body evidence exceeds the 4 KiB window limit");
}
