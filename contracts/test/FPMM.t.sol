// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {MarketTestBase} from "./MarketTestBase.sol";
import {HeadlineMarket} from "../src/market/HeadlineMarket.sol";
import {MarketFactory} from "../src/market/MarketFactory.sol";
import {FPMM} from "../src/market/FPMM.sol";
import {EmailProof} from "../src/dkim/IDKIMVerifier.sol";

contract FPMMTest is MarketTestBase {
    HeadlineMarket market;
    FPMM fpmm;

    uint256 constant LIQ = 10_000e6;

    function setUp() public override {
        super.setUp();
        (market, fpmm) = createFundedMarket(LIQ); // funded by alice
    }

    function test_InitialFundingEqualOdds() public view {
        (uint256 yesBal, uint256 noBal) = fpmm.poolBalances();
        assertEq(yesBal, LIQ);
        assertEq(noBal, LIQ);
        assertEq(fpmm.balanceOf(alice), LIQ);
        assertEq(fpmm.marginalPrice(0), 0.5e18);
        assertEq(fpmm.marginalPrice(1), 0.5e18);
    }

    function test_InitialFundingWithHint() public {
        MarketFactory.CreateMarketParams memory p = defaultParams();
        p.initialLiquidity = 9000e6;
        p.distributionHint = new uint256[](2);
        p.distributionHint[0] = 3; // pool keeps 3x YES => YES cheap
        p.distributionHint[1] = 1;
        vm.startPrank(bob);
        usdc.approve(address(factory), 9000e6);
        (, FPMM f2) = factory.createMarket(p);
        vm.stopPrank();

        (uint256 yesBal, uint256 noBal) = f2.poolBalances();
        assertEq(yesBal, 9000e6);
        assertEq(noBal, 3000e6);
        // bob keeps the surplus NO tokens
        assertEq(ct.balanceOf(f2.noPositionId(), bob), 6000e6);
        assertEq(f2.marginalPrice(0), 0.25e18); // YES at 25¢
        assertEq(f2.marginalPrice(1), 0.75e18);
    }

    function test_BuyMovesPrice() public {
        uint256 invest = 1000e6;
        uint256 expected = fpmm.calcBuyAmount(invest, 0);

        vm.startPrank(bob);
        usdc.approve(address(fpmm), invest);
        uint256 bought = fpmm.buy(invest, 0, expected);
        vm.stopPrank();

        assertEq(bought, expected);
        assertEq(ct.balanceOf(fpmm.yesPositionId(), bob), bought);
        assertGt(fpmm.marginalPrice(0), 0.5e18); // buying YES pushed YES price up
        // sanity: ~1000 spent at ~50c => roughly 1900+ shares (minus fee + slippage)
        assertGt(bought, 1800e6);
        assertLt(bought, 2000e6);
    }

    function test_BuySlippageGuard() public {
        uint256 invest = 1000e6;
        uint256 expected = fpmm.calcBuyAmount(invest, 0);
        vm.startPrank(bob);
        usdc.approve(address(fpmm), invest);
        vm.expectRevert(bytes("FPMM: max slippage exceeded"));
        fpmm.buy(invest, 0, expected + 1);
        vm.stopPrank();
    }

    function test_SellRoundTrip() public {
        uint256 invest = 1000e6;
        vm.startPrank(bob);
        usdc.approve(address(fpmm), invest);
        uint256 bought = fpmm.buy(invest, 0, 0);

        // sell everything back for whatever it fetches: find return amount by probing
        uint256 ret = 900e6;
        while (true) {
            // decrease until the required tokens fit what bob holds
            uint256 needed = fpmm.calcSellAmount(ret, 0);
            if (needed <= bought) break;
            ret -= 10e6;
        }
        ct.setApprovalForAll(address(fpmm), true);
        uint256 balBefore = usdc.balanceOf(bob);
        uint256 sold = fpmm.sell(ret, 0, bought);
        vm.stopPrank();

        assertLe(sold, bought);
        assertEq(usdc.balanceOf(bob), balBefore + ret);
        // round trip must lose money (2% fee each way + price impact)
        assertLt(ret, invest);
    }

    function test_ConstantProductInvariantOnBuy() public {
        (uint256 y0, uint256 n0) = fpmm.poolBalances();
        uint256 kBefore = y0 * n0;

        vm.startPrank(bob);
        usdc.approve(address(fpmm), 5000e6);
        fpmm.buy(5000e6, 1, 0);
        vm.stopPrank();

        (uint256 y1, uint256 n1) = fpmm.poolBalances();
        assertGe(y1 * n1, kBefore); // rounding always favours the pool
        // fee also accrues on top, so k should strictly grow a bit
        assertGt(y1 * n1, kBefore);
    }

    function test_FeesAccrueToLPs() public {
        vm.startPrank(bob);
        usdc.approve(address(fpmm), 1000e6);
        fpmm.buy(1000e6, 0, 0);
        vm.stopPrank();

        // 2% of 1000 = 20 USDC to sole LP alice
        assertEq(fpmm.feesWithdrawableBy(alice), 20e6);
        uint256 before = usdc.balanceOf(alice);
        fpmm.withdrawFees(alice); // anyone can trigger; funds go to alice
        assertEq(usdc.balanceOf(alice) - before, 20e6);
        assertEq(fpmm.feesWithdrawableBy(alice), 0);
    }

    function test_LateFunderNotEntitledToPastFees() public {
        vm.startPrank(bob);
        usdc.approve(address(fpmm), 1000e6);
        fpmm.buy(1000e6, 0, 0);
        vm.stopPrank();

        // carol adds funding after fees accrued
        vm.startPrank(carol);
        usdc.approve(address(fpmm), 5000e6);
        fpmm.addFunding(5000e6, new uint256[](0), carol);
        vm.stopPrank();

        assertEq(fpmm.feesWithdrawableBy(carol), 0);
        assertEq(fpmm.feesWithdrawableBy(alice), 20e6);
    }

    function test_FollowOnFundingProportional() public {
        // move the price first so pool is imbalanced
        vm.startPrank(bob);
        usdc.approve(address(fpmm), 5000e6);
        fpmm.buy(5000e6, 0, 0);
        vm.stopPrank();

        (uint256 y0, uint256 n0) = fpmm.poolBalances();
        uint256 supply0 = fpmm.totalSupply();

        vm.startPrank(carol);
        usdc.approve(address(fpmm), 3000e6);
        uint256 minted = fpmm.addFunding(3000e6, new uint256[](0), carol);
        vm.stopPrank();

        (uint256 y1, uint256 n1) = fpmm.poolBalances();
        // ratio preserved (within rounding)
        assertApproxEqRel(y1 * n0, n1 * y0, 1e12);
        // carol got surplus tokens of the scarcer outcome back
        uint256 maxBal = y0 > n0 ? y0 : n0;
        assertEq(minted, (3000e6 * supply0) / maxBal);
    }

    function test_RemoveFundingReturnsProportionalTokensPlusFees() public {
        vm.startPrank(bob);
        usdc.approve(address(fpmm), 1000e6);
        fpmm.buy(1000e6, 0, 0);
        vm.stopPrank();

        (uint256 y0, uint256 n0) = fpmm.poolBalances();
        uint256 supply = fpmm.totalSupply();
        uint256 half = fpmm.balanceOf(alice) / 2;

        uint256 usdcBefore = usdc.balanceOf(alice);
        vm.prank(alice);
        fpmm.removeFunding(half);

        assertEq(ct.balanceOf(fpmm.yesPositionId(), alice), (y0 * half) / supply);
        assertEq(ct.balanceOf(fpmm.noPositionId(), alice), (n0 * half) / supply);
        assertEq(usdc.balanceOf(alice) - usdcBefore, 20e6); // fees auto-claimed
        assertEq(fpmm.balanceOf(alice), half);
    }

    function test_TradingBlockedAfterResolution() public {
        market.submitProof(
            0,
            makeProof(
                "nytimes.com",
                block.timestamp + 1 days,
                "nytdirect@nytimes.com",
                "Breaking News: Fed cuts rates by 25 basis points",
                "",
                "n1"
            )
        );
        market.submitProof(
            1,
            makeProof(
                "email.washingtonpost.com",
                block.timestamp + 1 days,
                "no-reply@email.washingtonpost.com",
                "Fed cuts rates: what it means",
                "",
                "n2"
            )
        );
        assertEq(uint256(market.resolution()), uint256(HeadlineMarket.Resolution.Yes));

        vm.startPrank(bob);
        usdc.approve(address(fpmm), 100e6);
        vm.expectRevert(bytes("FPMM: market resolved"));
        fpmm.buy(100e6, 0, 0);
        vm.stopPrank();

        // LP exit still works: remove funding then redeem positions
        uint256 shares = fpmm.balanceOf(alice);
        vm.startPrank(alice);
        fpmm.removeFunding(shares);
        uint256[] memory sets = new uint256[](2);
        sets[0] = 1;
        sets[1] = 2;
        ct.redeemPositions(usdc, market.conditionId(), sets);
        vm.stopPrank();
        assertEq(fpmm.totalSupply(), 0);
    }

    function test_NoLiquidityBuyReverts() public {
        (, FPMM empty) = createDefaultMarket();
        vm.startPrank(bob);
        usdc.approve(address(empty), 100e6);
        vm.expectRevert(bytes("FPMM: no liquidity"));
        empty.buy(100e6, 0, 0);
        vm.stopPrank();
    }
}
