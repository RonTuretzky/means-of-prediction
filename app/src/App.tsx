import { HashRouter, Route, Routes, useLocation } from "react-router-dom";
import type React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Header } from "./components/Header";
import { ToastProvider } from "./components/Toast";
import { WalletProvider } from "./lib/wallet";
import { IS_LOCAL, IS_TESTNET } from "./config";
import { CreatePage } from "./pages/CreatePage";
import { LandingPage } from "./pages/LandingPage";
import { MarketPage } from "./pages/MarketPage";
import { MarketsPage } from "./pages/MarketsPage";
import { PortfolioPage } from "./pages/PortfolioPage";
import { ComputeDemosPage } from "./pages/ComputeDemosPage";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 1000 } },
});

function Page({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  return (
    <main key={pathname} data-page>
      {children}
    </main>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <WalletProvider>
        <ToastProvider>
        <HashRouter>
          <div className="min-h-screen">
            <Header />
            <Routes>
              <Route path="/" element={<Page><LandingPage /></Page>} />
              <Route path="/markets" element={<Page><MarketsPage /></Page>} />
              <Route path="/market/:id" element={<Page><MarketPage /></Page>} />
              <Route path="/create" element={<Page><CreatePage /></Page>} />
              <Route path="/portfolio" element={<Page><PortfolioPage /></Page>} />
              <Route path="/demos" element={<Page><ComputeDemosPage /></Page>} />
            </Routes>
            <footer className="mt-12 border-t-2 border-surface-ink bg-paper-0 px-4 py-6 text-center text-caption text-surface-grey-2">
              Means of Prediction — markets settled by real DKIM (RSA-SHA256) signatures verified onchain,
              Conditional Tokens settlement à la Polymarket.{" "}
              {IS_LOCAL
                ? "Local demo on anvil."
                : IS_TESTNET
                  ? "Live on Sepolia testnet — free Sepolia ETH + faucet USDC to try everything."
                  : "Live on Gnosis mainnet — connect a wallet to trade."}
            </footer>
          </div>
        </HashRouter>
        </ToastProvider>
      </WalletProvider>
    </QueryClientProvider>
  );
}
