import { useQuery } from "@tanstack/react-query";
import type { Address, Hex } from "viem";
import { parseAbiItem } from "viem";
import { abis } from "../contracts/gen";
import { deployment, DEPLOY_BLOCK } from "../config";
import { publicClient } from "../lib/wallet";
import { readPoolFeeConfiguration, readProtocolFeeConfiguration } from "../lib/fees";

export const FACTORY = deployment.factory as Address;
export const CT = deployment.conditionalTokens as Address;
export const USDC = deployment.usdc as Address;
export const DKIM = deployment.dkimRegistry as Address;

export enum Resolution {
  Unresolved = 0,
  Yes = 1,
  No = 2,
}

export enum ContentField {
  Subject = 0,
  Body = 1,
  SubjectOrBody = 2,
}

export interface Source {
  name: string;
  dkimDomain: string;
  fromRegex: string;
  contentRegex: string;
}

export interface Evidence {
  sourceIndex: number;
  submitter: Address;
  emailTimestamp: bigint;
  nullifier: Hex;
  subject: string;
}

export interface MarketData {
  id: number;
  market: Address;
  fpmm: Address;
  question: string;
  description: string;
  contentRegex: string;
  contentField: ContentField;
  sources: Source[];
  sourceMatched: boolean[];
  evidence: Evidence[];
  threshold: number;
  matchedCount: number;
  resolution: Resolution;
  windowStart: bigint;
  deadline: bigint;
  resolutionBuffer: bigint;
  creator: Address;
  createdAt: bigint;
  conditionId: Hex;
  yesPositionId: bigint;
  noPositionId: bigint;
  collateral: { address: Address; symbol: string; decimals: number };
  fee: bigint; // LP fee, 1e18-scale
  protocolFee: bigint | null; // null means unverified, never silently fee-free
  totalFee: bigint | null;
  feeRecipient: Address | null;
  feeError: string | null;
  legacyFees: boolean;
  priceYes: bigint; // 1e18
  priceNo: bigint;
  poolYes: bigint;
  poolNo: bigint;
  lpSupply: bigint;
  volume: bigint; // sum of buy investments + sell returns (collateral units)
  chainNow: bigint; // latest block timestamp (anvil time can differ from wall clock)
}

const buyEvent = parseAbiItem(
  "event Buy(address indexed buyer, uint256 investmentAmount, uint256 feeAmount, uint256 outcomeIndex, uint256 tokensBought)",
);
const sellEvent = parseAbiItem(
  "event Sell(address indexed seller, uint256 returnAmount, uint256 feeAmount, uint256 outcomeIndex, uint256 tokensSold)",
);


async function fetchMarket(id: number, market: Address, fpmm: Address, chainNow: bigint): Promise<MarketData> {
  const m = { address: market, abi: abis.HeadlineMarket } as const;
  const f = { address: fpmm, abi: abis.FPMM } as const;

  const [
    question,
    description,
    contentRegex,
    contentField,
    sources,
    evidence,
    threshold,
    matchedCount,
    resolution,
    windowStart,
    deadline,
    resolutionBuffer,
    creator,
    createdAt,
    conditionId,
    yesPositionId,
    noPositionId,
    collateralAddr,
    fee,
    priceYes,
    priceNo,
    pool,
    lpSupply,
  ] = (await publicClient.multicall({
    allowFailure: false,
    contracts: [
      { ...m, functionName: "question" },
      { ...m, functionName: "description" },
      { ...m, functionName: "contentRegex" },
      { ...m, functionName: "contentField" },
      { ...m, functionName: "getSources" },
      { ...m, functionName: "getEvidence" },
      { ...m, functionName: "threshold" },
      { ...m, functionName: "matchedCount" },
      { ...m, functionName: "resolution" },
      { ...m, functionName: "windowStart" },
      { ...m, functionName: "deadline" },
      { ...m, functionName: "resolutionBuffer" },
      { ...m, functionName: "creator" },
      { ...m, functionName: "createdAt" },
      { ...m, functionName: "conditionId" },
      { ...m, functionName: "yesPositionId" },
      { ...m, functionName: "noPositionId" },
      { ...m, functionName: "collateralToken" },
      { ...f, functionName: "fee" },
      { ...f, functionName: "marginalPrice", args: [0n] },
      { ...f, functionName: "marginalPrice", args: [1n] },
      { ...f, functionName: "poolBalances" },
      { ...f, functionName: "totalSupply" },
    ],
  })) as unknown[] as [
    string,
    string,
    string,
    number,
    Source[],
    Evidence[],
    number,
    bigint,
    number,
    bigint,
    bigint,
    bigint,
    Address,
    bigint,
    Hex,
    bigint,
    bigint,
    Address,
    bigint,
    bigint,
    bigint,
    [bigint, bigint],
    bigint,
  ];

  let feeConfiguration: Awaited<ReturnType<typeof readPoolFeeConfiguration>> | null = null;
  let feeError: string | null = null;
  try {
    feeConfiguration = await readPoolFeeConfiguration(publicClient, fpmm, abis.FPMM, fee);
  } catch (error) {
    feeError = error instanceof Error ? error.message.split("\n")[0] : "Platform fees could not be verified.";
  }

  const [symbol, decimals] = (await publicClient.multicall({
    allowFailure: false,
    contracts: [
      { address: collateralAddr, abi: abis.TestUSDC, functionName: "symbol" },
      { address: collateralAddr, abi: abis.TestUSDC, functionName: "decimals" },
    ],
  })) as [string, number];

  const sourceMatched = (await publicClient.multicall({
    allowFailure: false,
    contracts: sources.map((_, i) => ({ ...m, functionName: "sourceMatched", args: [BigInt(i)] })),
  })) as unknown as boolean[];

  // An FPMM that has never held liquidity cannot have trades — skip the log scans
  // (most of the board is 0-liquidity markets; this keeps public-RPC load tiny).
  const [buys, sells] =
    lpSupply === 0n && pool[0] === 0n && pool[1] === 0n
      ? [[], []]
      : await Promise.all([
          publicClient.getLogs({ address: fpmm, event: buyEvent, fromBlock: DEPLOY_BLOCK }),
          publicClient.getLogs({ address: fpmm, event: sellEvent, fromBlock: DEPLOY_BLOCK }),
        ]);
  const volume =
    buys.reduce((a, l) => a + (l.args.investmentAmount ?? 0n), 0n) +
    sells.reduce((a, l) => a + (l.args.returnAmount ?? 0n), 0n);

  return {
    id,
    market,
    fpmm,
    question,
    description,
    contentRegex,
    contentField: contentField as ContentField,
    sources: sources.map((s) => ({ ...s })),
    sourceMatched,
    evidence: evidence.map((e) => ({ ...e, sourceIndex: Number(e.sourceIndex) })),
    threshold: Number(threshold),
    matchedCount: Number(matchedCount),
    resolution: resolution as Resolution,
    windowStart,
    deadline,
    resolutionBuffer,
    creator,
    createdAt,
    conditionId,
    yesPositionId,
    noPositionId,
    collateral: { address: collateralAddr, symbol, decimals: Number(decimals) },
    fee,
    protocolFee: feeConfiguration?.protocolFee ?? null,
    totalFee: feeConfiguration?.totalFee ?? null,
    feeRecipient: feeConfiguration?.feeRecipient ?? null,
    feeError,
    legacyFees: feeConfiguration?.legacy ?? false,
    priceYes,
    priceNo,
    poolYes: pool[0],
    poolNo: pool[1],
    lpSupply,
    volume,
    chainNow,
  };
}

export function useMarkets() {
  return useQuery({
    queryKey: ["markets"],
    // Dozens of markets on a public RPC: poll gently (writes invalidate instantly anyway).
    refetchInterval: 12000,
    staleTime: 4000,
    queryFn: async () => {
      const [records, block] = await Promise.all([
        publicClient.readContract({
          address: FACTORY,
          abi: abis.MarketFactory,
          functionName: "getAllMarkets",
        }) as Promise<{ market: Address; fpmm: Address }[]>,
        publicClient.getBlock(),
      ]);
      return Promise.all(records.map((r, i) => fetchMarket(i, r.market, r.fpmm, block.timestamp)));
    },
  });
}

export function useMarket(id: number) {
  const { data: markets, ...rest } = useMarkets();
  return { data: markets?.[id], ...rest };
}

export function useBalances(account: Address, market?: MarketData) {
  return useQuery({
    queryKey: ["balances", account, market?.id],
    enabled: !!market,
    refetchInterval: 3000,
    queryFn: async () => {
      if (!market) throw new Error("no market");
      const [cash, yes, no, lp, fees, payoutDen, payoutYes, payoutNo] = (await publicClient.multicall({
        allowFailure: false,
        contracts: [
          { address: market.collateral.address, abi: abis.TestUSDC, functionName: "balanceOf", args: [account] },
          { address: CT, abi: abis.ConditionalTokens, functionName: "balanceOf", args: [market.yesPositionId, account] },
          { address: CT, abi: abis.ConditionalTokens, functionName: "balanceOf", args: [market.noPositionId, account] },
          { address: market.fpmm, abi: abis.FPMM, functionName: "balanceOf", args: [account] },
          { address: market.fpmm, abi: abis.FPMM, functionName: "feesWithdrawableBy", args: [account] },
          { address: CT, abi: abis.ConditionalTokens, functionName: "payoutDenominator", args: [market.conditionId] },
          { address: CT, abi: abis.ConditionalTokens, functionName: "payoutNumerators", args: [market.conditionId, 0n] },
          { address: CT, abi: abis.ConditionalTokens, functionName: "payoutNumerators", args: [market.conditionId, 1n] },
        ],
      })) as [bigint, bigint, bigint, bigint, bigint, bigint, bigint, bigint];
      return { cash, yes, no, lp, fees, payoutDen, payoutYes, payoutNo };
    },
  });
}

export function useCash(account: Address) {
  return useQuery({
    queryKey: ["cash", account],
    refetchInterval: 3000,
    queryFn: () =>
      publicClient.readContract({
        address: USDC,
        abi: abis.TestUSDC,
        functionName: "balanceOf",
        args: [account],
      }) as Promise<bigint>,
  });
}

export function useFactoryFees() {
  return useQuery({
    queryKey: ["factory-fees", FACTORY],
    refetchInterval: 12000,
    staleTime: 4000,
    queryFn: () => readProtocolFeeConfiguration(publicClient, FACTORY, abis.MarketFactory, "factory"),
  });
}
