// Real DKIM parsing + relaxed/relaxed canonicalization (RFC 6376), browser-safe (pure
// string ops; no Node crypto). Byte-verified against mailauth and against the real NYT
// email's signature, so the `header` bytes it produces are exactly what the sender's
// RSA key signed — the onchain DKIMVerifier does the actual RSA check over these bytes.
//
// The single source of canonicalization truth: the prover (browser) and the Node
// fixture-signer both import this so a signed fixture always re-canonicalizes identically.
import { keccak256, type Hex } from "viem";
import { canonicalizeBody, signedBodyEncoding, decodeBodyWindow } from "./body.ts";

export interface ParsedDkim {
  domain: string; // d=
  selector: string; // s=
  algo: string; // a=
  headerBytes: Uint8Array; // canonicalized signed headers (the RSA-signed message)
  signature: Uint8Array; // RSA signature (b=), raw bytes
  fromAddress: string;
  subject: string;
  bodyExcerpt: string;
  canonicalBody: Uint8Array;
  bodyEncoding: number;
  bodyError?: string;
  timestamp: number; // Date header as unix seconds
  nullifier: Hex; // keccak256(signature)
}


function latin1ToBytes(s: string): Uint8Array {
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i) & 0xff;
  return out;
}

function b64ToBytes(b64: string): Uint8Array {
  const bin = typeof atob === "function" ? atob(b64) : nodeAtob(b64);
  return latin1ToBytes(bin);
}
function nodeAtob(b64: string): string {
  const B = (globalThis as { Buffer?: { from(s: string, e: string): { toString(e: string): string } } }).Buffer;
  return B!.from(b64, "base64").toString("latin1");
}

/** Relaxed header canonicalization of one header field (RFC 6376 §3.4.2). */
function relaxHeader(name: string, value: string): string {
  return (
    name.toLowerCase().replace(/\s+$/, "") +
    ":" +
    value
      .replace(/[ \t]*\r?\n[ \t]*/g, " ") // unfold: folding WSP -> single SP
      .replace(/[ \t]+/g, " ") // collapse runs of WSP
      .replace(/^ /, "")
      .replace(/ $/, "")
  );
}

/**
 * Parse a raw .eml and produce the canonicalized signed header bytes + signature. Reads
 * the email as latin1 so every octet round-trips (DKIM operates on octets as transferred).
 */
export function parseDkimEmail(raw: string): ParsedDkim {
  const norm = raw.replace(/\r\n/g, "\n");
  const split = norm.indexOf("\n\n");
  const headerBlock = split === -1 ? norm : norm.slice(0, split);
  const body = split === -1 ? "" : norm.slice(split + 2);

  // fold continuation lines back into their header
  const lines: string[] = [];
  for (const line of headerBlock.split("\n")) {
    if (/^[ \t]/.test(line) && lines.length) lines[lines.length - 1] += "\n" + line;
    else lines.push(line);
  }
  const headers = lines.map((l) => {
    const i = l.indexOf(":");
    return { name: l.slice(0, i), value: l.slice(i + 1), lc: l.slice(0, i).toLowerCase(), used: false };
  });

  const dkimLine = lines.find((l) => /^dkim-signature:/i.test(l));
  if (!dkimLine) throw new Error("No DKIM-Signature header — this email is not DKIM-signed");
  const tags: Record<string, string> = {};
  dkimLine
    .slice(dkimLine.indexOf(":") + 1)
    .split(";")
    .forEach((kv) => {
      const i = kv.indexOf("=");
      if (i > 0) {
        const k = kv.slice(0, i).trim();
        let v = kv.slice(i + 1).trim();
        if (k === "b" || k === "bh") v = v.replace(/\s+/g, "");
        tags[k] = v;
      }
    });
  const hlist = tags.h.split(":").map((x) => x.trim());

  // build the signed data: each h= entry consumes the bottom-most unused matching
  // header; over-signed / missing entries contribute the null string.
  let signed = "";
  for (const hn of hlist) {
    const c = [...headers].reverse().find((x) => x.lc === hn.toLowerCase() && !x.used);
    if (c) {
      c.used = true;
      signed += relaxHeader(c.name, c.value) + "\r\n";
    }
  }
  // the DKIM-Signature header itself, with the b= value emptied, no trailing CRLF
  const dName = dkimLine.slice(0, dkimLine.indexOf(":"));
  const dVal = dkimLine.slice(dkimLine.indexOf(":") + 1);
  signed += relaxHeader(dName, dVal.replace(/\bb=[^;]*/, "b="));

  const signature = b64ToBytes(tags.b);
  const nullifier = keccak256(signature);

  // extracted display/matching fields
  const rawHeader = (name: string) => headers.find((h) => h.lc === name)?.value ?? "";
  const fromHeader = rawHeader("from");
  const fromMatch = fromHeader.match(/<([^>]+)>/) ?? fromHeader.match(/([^\s<>"]+@[^\s<>"]+)/);
  const fromAddress = (fromMatch?.[1] ?? "").trim();
  const subject = decodeSubject(rawHeader("subject").replace(/[ \t]*\r?\n[ \t]*/g, " ").trim());
  const timestamp = Math.floor(new Date(rawHeader("date").replace(/[ \t]*\r?\n[ \t]*/g, " ").trim()).getTime() / 1000);

  let canonicalBody = new Uint8Array(0), bodyEncoding = 1, bodyExcerpt = "", bodyError: string | undefined;
  try {
    if (Object.hasOwn(tags, "l")) throw new Error("DKIM l= partial-body signatures cannot authenticate a body proof");
    const [headerCanon, bodyCanon] = (tags.c ?? "simple/simple").split("/");
    if (headerCanon !== "relaxed") throw new Error("Only relaxed DKIM headers are supported");
    canonicalBody = canonicalizeBody(body, bodyCanon ?? "simple");
    bodyEncoding = signedBodyEncoding(signed);
    if (canonicalBody.length) bodyExcerpt = new TextDecoder("utf-8", { fatal: true }).decode(decodeBodyWindow(canonicalBody, 0, canonicalBody.length, bodyEncoding, false));
  } catch (e) { bodyError = e instanceof Error ? e.message : String(e); }

  return {
    domain: tags.d,
    selector: tags.s,
    algo: tags.a ?? "rsa-sha256",
    headerBytes: latin1ToBytes(signed),
    signature,
    fromAddress,
    subject,
    bodyExcerpt,
    canonicalBody, bodyEncoding, bodyError,
    timestamp,
    nullifier,
  };
}

function decodeQuotedPrintable(s: string): string {
  const noSoft = s.replace(/=\r?\n/g, "");
  const bytes: number[] = [];
  for (let i = 0; i < noSoft.length; i++) {
    if (noSoft[i] === "=" && /[0-9A-Fa-f]{2}/.test(noSoft.slice(i + 1, i + 3))) {
      bytes.push(parseInt(noSoft.slice(i + 1, i + 3), 16));
      i += 2;
    } else for (const b of new TextEncoder().encode(noSoft[i])) bytes.push(b);
  }
  return new TextDecoder("utf-8").decode(new Uint8Array(bytes));
}

function decodeSubject(s: string): string {
  const collapsed = s.replace(/(=\?[^?]+\?[QqBb]\?[^?]*\?=)\s+(?==\?)/g, "$1");
  return collapsed.replace(/=\?([^?]+)\?([QqBb])\?([^?]*)\?=/g, (_, charset: string, enc: string, text: string) => {
    let bytes: number[];
    if (enc.toUpperCase() === "B") {
      try {
        bytes = Array.from(b64ToBytes(text));
      } catch {
        return text;
      }
    } else {
      bytes = [];
      const q = text.replace(/_/g, " ");
      for (let i = 0; i < q.length; i++) {
        if (q[i] === "=" && /[0-9A-Fa-f]{2}/.test(q.slice(i + 1, i + 3))) {
          bytes.push(parseInt(q.slice(i + 1, i + 3), 16));
          i += 2;
        } else for (const b of new TextEncoder().encode(q[i])) bytes.push(b);
      }
    }
    try {
      return new TextDecoder(charset.toLowerCase().includes("8859") ? "iso-8859-1" : "utf-8").decode(
        new Uint8Array(bytes),
      );
    } catch {
      return new TextDecoder("utf-8").decode(new Uint8Array(bytes));
    }
  });
}

export function bytesToHex(b: Uint8Array): Hex {
  let s = "0x";
  for (const x of b) s += x.toString(16).padStart(2, "0");
  return s as Hex;
}
