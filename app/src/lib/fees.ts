import { toFunctionSelector, zeroAddress, type Abi, type Address, type Hex } from "viem";

export const FEE_SCALE = 10n ** 18n;
const PERCENT_SCALE = 10n ** 16n;

/** Parse percent input exactly; never round, truncate, or accept scientific notation. */
export function parseFeePercent(input: string): bigint | null {
  const value = input.trim();
  if (!/^(?:\d+(?:\.\d{0,16})?|\.\d{1,16})$/.test(value)) return null;
  const [whole = "", fraction = ""] = value.split(".");
  const fee = BigInt(whole || "0") * PERCENT_SCALE + BigInt(fraction.padEnd(16, "0"));
  return fee < FEE_SCALE ? fee : null;
}

export function formatFeePercent(fee: bigint): string {
  const whole = fee / PERCENT_SCALE;
  const fraction = (fee % PERCENT_SCALE).toString().padStart(16, "0").replace(/0+$/, "");
  return `${whole}${fraction ? `.${fraction}` : ""}`;
}

export function validateTradingFees(lpFee: bigint | null, protocolFee: bigint): string | null {
  if (lpFee === null || lpFee < 0n || lpFee >= FEE_SCALE) {
    return "Enter an LP fee from 0% to less than 100%, with up to 16 decimal places.";
  }
  if (protocolFee < 0n || protocolFee >= FEE_SCALE || lpFee + protocolFee >= FEE_SCALE) {
    return "The LP fee plus the platform fee must be less than 100%.";
  }
  return null;
}

export interface FeeReader {
  getBytecode(args: { address: Address }): Promise<Hex | undefined>;
  readContract(args: { address: Address; abi: Abi; functionName: string }): Promise<unknown>;
}

export interface ProtocolFeeConfiguration {
  protocolFee: bigint;
  feeRecipient: Address;
  legacy: boolean;
}

type Kind = "pool" | "factory";
type Support = "legacy" | "platform";
const supportCache = new WeakMap<FeeReader, Map<string, Promise<Support>>>();
const selector = (signature: string) => toFunctionSelector(signature).slice(2).toLowerCase();
// These deployed contracts use Solidity PUSH4 function dispatch. Only classify a
// legacy contract after identifying its existing interface and BOTH absent getters.
const hasSelector = (code: string, signature: string) => code.includes(`63${selector(signature)}`);

async function inspectSupport(client: FeeReader, address: Address, kind: Kind): Promise<Support> {
  let code = (await client.getBytecode({ address }))?.toLowerCase();
  if (!code || code === "0x") throw new Error("No contract code found while checking platform fees.");
  // FPMMs are immutable, standard EIP-1167 clones. Read the actual implementation,
  // not the tiny proxy runtime. Unknown proxy layouts are never assumed fee-free.
  const clone = code.match(/^0x363d3d373d3d3d363d73([0-9a-f]{40})5af43d82803e903d91602b57fd5bf3$/);
  if (clone) {
    code = (await client.getBytecode({ address: `0x${clone[1]}` }))?.toLowerCase();
    if (!code || code === "0x") throw new Error("Pool implementation code is unavailable.");
  }
  const protocol = hasSelector(code, "protocolFee()");
  const recipient = hasSelector(code, "feeRecipient()");
  if (protocol && recipient) return "platform";
  if (protocol || recipient) throw new Error("Incomplete platform fee interface; fees could not be verified.");
  const knownLegacy = kind === "pool"
    ? hasSelector(code, "fee()") && hasSelector(code, "calcBuyAmount(uint256,uint256)") && hasSelector(code, "calcSellAmount(uint256,uint256)")
    : hasSelector(code, "marketCount()") && hasSelector(code, "getAllMarkets()");
  if (!knownLegacy) throw new Error("Unrecognized contract interface; platform fees could not be verified.");
  return "legacy";
}

/** Cache immutable code capabilities only. RPC errors are not cached as legacy. */
function feeSupport(client: FeeReader, address: Address, kind: Kind): Promise<Support> {
  let cache = supportCache.get(client);
  if (!cache) { cache = new Map(); supportCache.set(client, cache); }
  const key = `${kind}:${address.toLowerCase()}`;
  let result = cache.get(key);
  if (!result) {
    result = inspectSupport(client, address, kind).catch((error) => {
      cache!.delete(key);
      throw error;
    });
    cache.set(key, result);
  }
  return result;
}

/** A failed getter (including viem's underlying multicall) is an error, never 0%. */
export async function readProtocolFeeConfiguration(
  client: FeeReader, address: Address, abi: Abi, kind: Kind,
): Promise<ProtocolFeeConfiguration> {
  const support = await feeSupport(client, address, kind);
  if (support === "legacy") return { protocolFee: 0n, feeRecipient: zeroAddress, legacy: true };
  const [protocolFee, feeRecipient] = await Promise.all([
    client.readContract({ address, abi, functionName: "protocolFee" }),
    client.readContract({ address, abi, functionName: "feeRecipient" }),
  ]);
  if (typeof protocolFee !== "bigint" || protocolFee < 0n || protocolFee >= FEE_SCALE
    || typeof feeRecipient !== "string" || !/^0x[0-9a-f]{40}$/i.test(feeRecipient)
    || (protocolFee > 0n && feeRecipient.toLowerCase() === zeroAddress)) {
    throw new Error("Invalid onchain platform fee configuration.");
  }
  return { protocolFee, feeRecipient: feeRecipient as Address, legacy: false };
}

export async function readPoolFeeConfiguration(client: FeeReader, address: Address, abi: Abi, lpFee: bigint) {
  const config = await readProtocolFeeConfiguration(client, address, abi, "pool");
  const totalFee = config.legacy ? lpFee : await client.readContract({ address, abi, functionName: "totalFee" });
  if (validateTradingFees(lpFee, config.protocolFee) || typeof totalFee !== "bigint" || totalFee !== lpFee + config.protocolFee) {
    throw new Error("Onchain trading fees do not match; trading is paused until they can be verified.");
  }
  return { ...config, totalFee };
}
