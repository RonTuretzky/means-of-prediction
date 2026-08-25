// Wallet layer. On the local chain (anvil) it uses the well-known dev accounts with a
// header switcher. On a real chain (Gnosis) it connects the browser's injected wallet
// (MetaMask/Rabby/…) and sends real transactions.
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import {
  createPublicClient,
  createWalletClient,
  custom,
  fallback,
  http,
  numberToHex,
  publicActions,
  type Abi,
  type Address,
  type PublicClient,
  type Transport,
} from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { useQueryClient } from "@tanstack/react-query";
import { chain, CHAIN_ID, DEV_ACCOUNTS, IS_LOCAL, RPC_URL } from "../config";

// Reads never go through the user's wallet: the site must work for someone who has
// never connected one, so it talks to public RPCs directly.
//
// Those public RPCs disagree wildly about eth_getLogs. Our scans start at the
// deployment block — a window that grows every day — and publicnode rejects ranges
// over 50k blocks on some pool nodes and 10k on others, drpc caps at 10k, 1rpc at 50.
// So: try several providers in order, and split every oversized eth_getLogs into
// windows small enough that any of them will serve it. HTTP batching folds the
// windows back into roughly one round trip, so the extra calls are close to free.
const MAX_LOG_RANGE = 9_000n;

/** Read endpoints per chain, best-first (VITE_RPC_URL overrides). */
const READ_RPCS: Record<number, string[]> = {
  // no getLogs range cap, serves batched requests
  100: ["https://rpc.gnosischain.com", "https://gnosis-rpc.publicnode.com"],
  // publicnode last: it answers Sepolia log scans with an empty set rather than an error
  11155111: [
    "https://rpc.sepolia.ethpandaops.io",
    "https://sepolia.gateway.tenderly.co",
    "https://ethereum-sepolia-rpc.publicnode.com",
  ],
};

function readUrls(): string[] {
  const override = import.meta.env.VITE_RPC_URL as string | undefined;
  if (override) return [override];
  return READ_RPCS[CHAIN_ID] ?? [RPC_URL];
}

function asBlockNumber(v: unknown): bigint | null {
  if (typeof v === "bigint") return v;
  if (typeof v === "string" && v.startsWith("0x")) return BigInt(v);
  if (v === "earliest") return 0n;
  return null; // "latest"/"pending"/undefined — resolved by the caller
}

/** Splits oversized eth_getLogs into MAX_LOG_RANGE windows; passes everything else through. */
function withChunkedLogs(inner: Transport): Transport {
  return (opts) => {
    const t = inner(opts);
    const request = async (args: { method: string; params?: unknown }, reqOpts?: unknown) => {
      const call = (a: unknown) => (t.request as (a: unknown, o?: unknown) => Promise<unknown>)(a, reqOpts);
      if (args.method !== "eth_getLogs") return call(args);

      const filter = ((args.params as Record<string, unknown>[]) ?? [])[0] ?? {};
      const from = asBlockNumber(filter.fromBlock);
      if (from === null) return call(args); // no explicit start — leave it to the node
      const to = asBlockNumber(filter.toBlock) ?? BigInt((await call({ method: "eth_blockNumber" })) as string);
      if (to <= from + MAX_LOG_RANGE) return call(args);

      const windows: Array<[bigint, bigint]> = [];
      for (let start = from; start <= to; start += MAX_LOG_RANGE + 1n) {
        const end = start + MAX_LOG_RANGE > to ? to : start + MAX_LOG_RANGE;
        windows.push([start, end]);
      }
      // HTTP batching folds these into a single round trip
      const parts = await Promise.all(
        windows.map(([start, end]) =>
          call({ ...args, params: [{ ...filter, fromBlock: numberToHex(start), toBlock: numberToHex(end) }] }),
        ),
      );
      return (parts as unknown[][]).flat();
    };
    return { ...t, request: request as typeof t.request };
  };
}

const readTransport = withChunkedLogs(
  IS_LOCAL
    ? http(RPC_URL, { batch: { batchSize: 20, wait: 16 } })
    : fallback(
        readUrls().map((url) => http(url, { batch: { batchSize: 20, wait: 16 } })),
        { rank: false, retryCount: 1 },
      ),
);

// JSON-RPC batching (HTTP batch + auto-multicall aggregation) keeps the request
// count sane with dozens of markets on a public rate-limited RPC.
export const publicClient: PublicClient = createPublicClient({
  chain,
  batch: { multicall: { wait: 16 } },
  transport: readTransport,
});

type Eip1193 = { request(args: { method: string; params?: unknown[] }): Promise<unknown> };
const injected = (): Eip1193 | undefined => (globalThis as { ethereum?: Eip1193 }).ethereum;

interface WalletCtx {
  isLocal: boolean;
  accountIndex: number;
  accountName: string;
  address: Address;
  connected: boolean;
  setAccountIndex: (i: number) => void;
  connect: () => Promise<void>;
  write: (args: { address: Address; abi: Abi; functionName: string; args?: readonly unknown[]; value?: bigint }) => Promise<void>;
}

const Ctx = createContext<WalletCtx | null>(null);

export function WalletProvider({ children }: { children: ReactNode }) {
  const [accountIndex, setAccountIndex] = useState(0);
  const [injectedAddress, setInjectedAddress] = useState<Address | null>(null);
  const queryClient = useQueryClient();

  const connect = useCallback(async () => {
    const eth = injected();
    if (!eth) throw new Error("No browser wallet found — install MetaMask or Rabby");
    const accounts = (await eth.request({ method: "eth_requestAccounts" })) as Address[];
    // ensure the wallet is on Gnosis (chain 100)
    const hexId = `0x${chain.id.toString(16)}`;
    try {
      await eth.request({ method: "wallet_switchEthereumChain", params: [{ chainId: hexId }] });
    } catch {
      /* user may reject or chain already selected */
    }
    setInjectedAddress(accounts[0] ?? null);
  }, []);

  const value = useMemo<WalletCtx>(() => {
    const localAccount = IS_LOCAL ? privateKeyToAccount(DEV_ACCOUNTS[accountIndex].pk) : null;
    const address = (IS_LOCAL ? localAccount!.address : (injectedAddress ?? "0x0000000000000000000000000000000000000000")) as Address;

    const walletClient = () => {
      if (IS_LOCAL) {
        return createWalletClient({ account: localAccount!, chain, transport: http(RPC_URL) }).extend(publicActions);
      }
      const eth = injected();
      if (!eth || !injectedAddress) throw new Error("Connect a wallet first");
      return createWalletClient({ account: injectedAddress, chain, transport: custom(eth) }).extend(publicActions);
    };

    return {
      isLocal: IS_LOCAL,
      accountIndex,
      accountName: IS_LOCAL ? DEV_ACCOUNTS[accountIndex].name : shortAddr(injectedAddress),
      address,
      connected: IS_LOCAL || !!injectedAddress,
      setAccountIndex,
      connect,
      write: async ({ address: to, abi, functionName, args, value }) => {
        const wc = walletClient();
        const { request } = await wc.simulateContract({
          address: to,
          abi,
          functionName,
          args: args ?? [],
          account: (IS_LOCAL ? localAccount! : injectedAddress) as Address,
          value,
        });
        const hash = await wc.writeContract(request);
        const receipt = await wc.waitForTransactionReceipt({ hash });
        if (receipt.status !== "success") throw new Error("Transaction reverted");
        await queryClient.invalidateQueries();
      },
    };
  }, [accountIndex, injectedAddress, connect, queryClient]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useWallet(): WalletCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useWallet outside WalletProvider");
  return ctx;
}

function shortAddr(a: Address | null): string {
  return a ? `${a.slice(0, 6)}…${a.slice(-4)}` : "Connect";
}
