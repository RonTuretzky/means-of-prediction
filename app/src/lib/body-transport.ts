import type { Hex } from "viem";

/** Immutable data-code pages. Each runtime is one STOP byte plus <=24,000 bytes. */
export function bodyPages(body: Hex): Hex[] {
  const length = (body.length - 2) / 2;
  if (!Number.isInteger(length) || length < 1 || length > 196608) throw new Error("Unsupported canonical body size");
  const pages: Hex[] = [];
  for (let i = 2; i < body.length; i += 48000) pages.push(`0x${body.slice(i, i + 48000)}`);
  return pages;
}
