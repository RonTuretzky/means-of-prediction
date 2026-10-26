import { useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { Button } from "@breadcoop/ui";
import { Wallet } from "@phosphor-icons/react";
import {
  AVAILABLE_NETWORKS,
  CHAIN_LABEL,
  DEV_ACCOUNTS,
  EXPLORER_URL,
  IS_LOCAL,
  IS_TESTNET,
  NETWORK,
  setNetwork,
} from "../config";
import { useWallet } from "../lib/wallet";
import { useCash, USDC } from "../hooks/useMarkets";
import { abis } from "../contracts/gen";
import { fmtAmount } from "../lib/format";
import { useToast } from "./Toast";

export function Header() {
  const { pathname } = useLocation();
  const showWallet = pathname === "/create" || pathname === "/markets" || pathname === "/portfolio" || pathname.startsWith("/market/");
  const wallet = useWallet();
  const toast = useToast();
  const { data: cash } = useCash(wallet.address);
  const [fauceting, setFauceting] = useState(false);
  const [connecting, setConnecting] = useState(false);

  const faucet = async () => {
    setFauceting(true);
    try {
      await wallet.write({ address: USDC, abi: abis.TestUSDC, functionName: "faucet" });
    } finally {
      setFauceting(false);
    }
  };

  const connect = async () => {
    setConnecting(true);
    try {
      await wallet.connect();
    } catch (e) {
      toast.push({ kind: "error", title: "Wallet connection failed", detail: (e as Error).message });
    } finally {
      setConnecting(false);
    }
  };

  const navClass = ({ isActive }: { isActive: boolean }) =>
    `mp-nav-link${isActive ? " active" : ""}`;

  return (
    <header className="mp-site-header">
      <div className="mp-header-inner">
        <Link to="/" className="mp-brand"><span className="mp-brand-mark" aria-hidden="true">↗</span>Means of Prediction</Link>
        <nav className="mp-site-nav" aria-label="Main navigation">
          <NavLink to="/markets" className={navClass}>
            Markets
          </NavLink>
          <NavLink to="/create/ai" className={navClass}>
            Draft rules
          </NavLink>
          <NavLink to="/demo/peace-2026" className={navClass}>
            Market replay
          </NavLink>
          <NavLink to="/demos" className={navClass}>
            Compute demos
          </NavLink>
          <details className="mp-more-nav"><summary aria-label="More navigation">More ▾</summary><div><NavLink to="/create" onClick={event => event.currentTarget.closest("details")?.removeAttribute("open")}>On-chain markets</NavLink><NavLink to="/portfolio" onClick={event => event.currentTarget.closest("details")?.removeAttribute("open")}>Portfolio</NavLink></div></details>
        </nav>

        {showWallet && <div className="mp-wallet-strip">
          <span className="mr-auto text-xs text-surface-grey-2">Market network: {CHAIN_LABEL}</span>
          {!IS_LOCAL && AVAILABLE_NETWORKS.filter((n) => n !== "local").length > 1 && (
            <select
              aria-label="Network"
              data-testid="network-switcher"
              className="border-2 border-surface-ink bg-paper-0 px-2 py-1.5 text-sm font-bold uppercase shadow-[0.125rem_0.125rem_0px_0px_#595959]"
              value={NETWORK}
              onChange={(e) => setNetwork(e.target.value as typeof NETWORK)}
            >
              {AVAILABLE_NETWORKS.filter((n) => n !== "local").map((n) => (
                <option key={n} value={n}>
                  {n === "gnosis" ? "Gnosis" : n === "sepolia" ? "Sepolia" : n}
                </option>
              ))}
            </select>
          )}
          {IS_TESTNET && wallet.connected && (
            <Button size="sm" variant="secondary" onClick={faucet} isLoading={fauceting} data-testid="faucet">
              Faucet +$10k
            </Button>
          )}
          {IS_LOCAL ? (
            <>
              <div className="text-right">
                <div className="text-caption text-surface-grey-2">Cash</div>
                <div className="font-bold" data-tabular data-testid="cash-balance">
                  {cash !== undefined ? fmtAmount(cash, 6) : "…"}
                </div>
              </div>
              <Button size="sm" variant="secondary" onClick={faucet} isLoading={fauceting} data-testid="faucet">
                Faucet +$10k
              </Button>
              <select
                aria-label="Dev account"
                data-testid="account-switcher"
                className="border-2 border-surface-ink bg-paper-0 px-2 py-1.5 text-sm font-bold shadow-[0.125rem_0.125rem_0px_0px_#595959]"
                value={wallet.accountIndex}
                onChange={(e) => wallet.setAccountIndex(Number(e.target.value))}
              >
                {DEV_ACCOUNTS.map((a, i) => (
                  <option key={a.name} value={i}>
                    {a.name}
                  </option>
                ))}
              </select>
            </>
          ) : wallet.connected ? (
            <a
              href={EXPLORER_URL ? `${EXPLORER_URL}/address/${wallet.address}` : "#"}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 border-2 border-surface-ink bg-paper-0 px-3 py-1.5 text-sm font-bold shadow-[0.125rem_0.125rem_0px_0px_#595959]"
            >
              <span className="h-2 w-2 rounded-full bg-system-green" /> {wallet.accountName}
            </a>
          ) : (
            <Button size="sm" leftIcon={<Wallet size={14} />} isLoading={connecting} onClick={connect} data-testid="connect">
              Connect wallet
            </Button>
          )}
        </div>}
      </div>
    </header>
  );
}
