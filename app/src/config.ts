import { defineChain, type Address } from "viem";
import { gnosis, sepolia } from "viem/chains";
import { defaultNetwork, deployments } from "./contracts/gen";

// ---------------------------------------------------------------------------
// Runtime network selection. The build embeds every real-network deployment
// (gnosis, sepolia) plus the DEPLOYMENT-selected default (local during dev).
// On a real-network build the user can switch networks from the header; the
// choice persists in localStorage and takes effect on reload (all config here
// is resolved once, at module init).
// ---------------------------------------------------------------------------

// Plain strings (not a literal union): which networks are embedded varies per
// build (local dev embeds "local"; the Pages build embeds gnosis+sepolia).
export type NetworkName = string;

const STORAGE_KEY = "mop-network";

export const AVAILABLE_NETWORKS: NetworkName[] = Object.keys(deployments);

function pickNetwork(): NetworkName {
  const def: string = defaultNetwork;
  // Local dev builds always target the local anvil deployment.
  if (def === "local") return "local";
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && stored !== "local" && stored in deployments) return stored;
  } catch {
    /* SSR / privacy mode */
  }
  return def;
}

export const NETWORK: NetworkName = pickNetwork();

/** Switch the app to another embedded deployment (persists, then reloads). */
export function setNetwork(name: NetworkName) {
  try {
    localStorage.setItem(STORAGE_KEY, name);
  } catch {
    /* ignore */
  }
  location.reload();
}

export const deployment = deployments[NETWORK as keyof typeof deployments] as {
  chainId: number;
  bodyParsingVersion?: number;
  emailBodyStore?: string;
  factory: string;
  conditionalTokens: string;
  usdc: string;
  dkimRegistry: string;
  verifier: string;
  multicall3: string;
  deployBlock?: number;
  /** LLMJudge oracle (judged markets); absent/null where the factory has no judge. */
  llmJudge?: string | null;
};

export const BODY_PARSING = deployment.bodyParsingVersion === 1;

export const CHAIN_ID = deployment.chainId as number;
export const IS_LOCAL = CHAIN_ID === 31337;
/** Public testnet: real chain + injected wallet, but faucet collateral. */
export const IS_TESTNET = CHAIN_ID === 11155111;

/** First block to scan for our contracts' logs (0 where the deployment predates the field). */
export const DEPLOY_BLOCK = BigInt(deployment.deployBlock ?? 0);

const DEFAULT_RPCS: Record<number, string> = {
  31337: "http://localhost:8547",
  100: "https://gnosis-rpc.publicnode.com",
  11155111: "https://ethereum-sepolia-rpc.publicnode.com",
};
export const RPC_URL = (import.meta.env.VITE_RPC_URL as string | undefined) ?? DEFAULT_RPCS[CHAIN_ID];

const localChain = defineChain({
  id: 31337,
  name: "Anvil",
  nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
  rpcUrls: { default: { http: [RPC_URL] } },
  contracts: { multicall3: { address: deployment.multicall3 as Address } },
});

const gnosisChain = defineChain({ ...gnosis, rpcUrls: { default: { http: [RPC_URL] } } });
const sepoliaChain = defineChain({ ...sepolia, rpcUrls: { default: { http: [RPC_URL] } } });

/** The chain the selected deployment lives on. */
export const chain = IS_LOCAL ? localChain : IS_TESTNET ? sepoliaChain : gnosisChain;

export const CHAIN_LABEL = IS_LOCAL ? "Local" : IS_TESTNET ? "Sepolia" : "Gnosis";

export const EXPLORER_URL = IS_LOCAL
  ? null
  : IS_TESTNET
    ? "https://eth-sepolia.blockscout.com"
    : "https://gnosisscan.io";

/// Anvil's canonical, publicly-known dev accounts (local only; never on a real network).
export const DEV_ACCOUNTS = [
  { name: "Alice", pk: "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d" as const },
  { name: "Bob", pk: "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a" as const },
  { name: "Carol", pk: "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6" as const },
];
