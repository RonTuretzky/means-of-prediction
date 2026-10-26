import { HashRouter, Link, Route, Routes, useLocation } from "react-router-dom";
import type React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Header } from "./components/Header";
import { ToastProvider } from "./components/Toast";
import { WalletProvider } from "./lib/wallet";
import { CreatePage } from "./pages/CreatePage";
import { LandingPage } from "./pages/LandingPage";
import { MarketPage } from "./pages/MarketPage";
import { MarketsPage } from "./pages/MarketsPage";
import { PortfolioPage } from "./pages/PortfolioPage";
import { ComputeDemosPage } from "./pages/ComputeDemosPage";
import { PeaceDemoPage } from "./pages/PeaceDemoPage";
import { RuleStudioPage } from "./pages/RuleStudioPage";
import "./product.css";

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
              <Route path="/create/ai" element={<Page><RuleStudioPage /></Page>} />
              <Route path="/portfolio" element={<Page><PortfolioPage /></Page>} />
              <Route path="/demos" element={<Page><ComputeDemosPage /></Page>} />
              <Route path="/demo/peace-2026" element={<Page><PeaceDemoPage /></Page>} />
            </Routes>
            <footer className="mp-footer"><div className="mp-footer-inner"><p><strong>Means of Prediction</strong>Rules you can read. Evidence you can inspect.</p><nav className="mp-footer-links" aria-label="Footer navigation"><Link to="/create/ai">Draft with DeepSeek</Link><Link to="/demo/peace-2026">Historical replay</Link><Link to="/demos">Sepolia component</Link><Link to="/create">On-chain markets</Link></nav></div></footer>
          </div>
        </HashRouter>
        </ToastProvider>
      </WalletProvider>
    </QueryClientProvider>
  );
}
