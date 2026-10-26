import { useQuery } from "@tanstack/react-query";
import type { ComputeDemo } from "../data/compute-demos";
import { readComputeDemo } from "../lib/compute-demos";

export function useComputeDemo(demo: ComputeDemo) {
  return useQuery({
    queryKey: ["compute-demo", demo.chainId, demo.contract, demo.settlementTx],
    queryFn: () => readComputeDemo(demo),
    staleTime: 60_000,
    retry: 1,
    refetchOnWindowFocus: false,
  });
}
