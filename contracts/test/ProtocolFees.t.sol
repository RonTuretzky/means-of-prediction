// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {MarketTestBase} from "./MarketTestBase.sol";
import {MarketFactory} from "../src/market/MarketFactory.sol";
import {HeadlineMarket} from "../src/market/HeadlineMarket.sol";
import {FPMM} from "../src/market/FPMM.sol";
import {ILLMJudge} from "../src/judge/ILLMJudge.sol";

contract ProtocolFeesTest is MarketTestBase {
    FPMM pool;
    address treasury = address(0xFEE);

    function setUp() public override {
        super.setUp();
        factory = new MarketFactory(ct, verifier, address(new HeadlineMarket()), address(new FPMM()),
            ILLMJudge(address(0)), 1e16, treasury);
        (, pool) = createFundedMarket(10_000e6);
    }

    function test_BuySeparatesPlatformAndLPFees() public {
        vm.startPrank(bob);
        usdc.approve(address(pool), 1000e6);
        uint256 quote = pool.calcBuyAmount(1000e6, 0);
        assertEq(pool.buy(1000e6, 0, quote), quote);
        vm.stopPrank();
        assertEq(pool.protocolFeesAccrued(), 10e6);
        assertEq(pool.feesWithdrawableBy(alice), 20e6);
        assertEq(usdc.balanceOf(address(pool)), 30e6);
        assertEq(pool.totalFee(), 3e16);
        vm.prank(carol);
        pool.withdrawProtocolFees();
        assertEq(usdc.balanceOf(treasury), 10e6);
        assertEq(pool.protocolFeesAccrued(), 0);
        pool.withdrawProtocolFees();
        pool.withdrawFees(alice);
        assertEq(usdc.balanceOf(address(pool)), 0);
    }

    function test_SellQuoteIncludesBothFeesAndPreservesCollateral() public {
        vm.startPrank(bob);
        usdc.approve(address(pool), 1000e6);
        pool.buy(1000e6, 0, 0);
        ct.setApprovalForAll(address(pool), true);
        uint256 quote = pool.calcSellAmount(500e6, 0);
        uint256 cash = usdc.balanceOf(bob);
        uint256 platformBefore = pool.protocolFeesAccrued();
        assertEq(pool.sell(500e6, 0, quote), quote);
        assertEq(usdc.balanceOf(bob) - cash, 500e6);
        vm.stopPrank();
        uint256 gross = (uint256(500e6) * 1e18 + (1e18 - 3e16) - 1) / (1e18 - 3e16);
        assertEq(pool.protocolFeesAccrued() - platformBefore, gross * 1e16 / 1e18);
        assertGe(usdc.balanceOf(address(pool)), pool.protocolFeesAccrued() + pool.feesWithdrawableBy(alice));
        uint256 shares = pool.balanceOf(alice);
        vm.prank(alice);
        pool.removeFunding(shares);
        pool.withdrawProtocolFees();
        assertEq(pool.protocolFeesAccrued(), 0);
    }

    function test_ZeroLPFeeStillChargesPlatform() public {
        MarketFactory.CreateMarketParams memory p = defaultParams();
        p.fee = 0;
        p.initialLiquidity = 1000e6;
        vm.startPrank(alice);
        usdc.approve(address(factory), p.initialLiquidity);
        (, FPMM f) = factory.createMarket(p);
        usdc.approve(address(f), 100e6);
        f.buy(100e6, 0, 0);
        vm.stopPrank();
        assertEq(f.protocolFeesAccrued(), 1e6);
        assertEq(f.feesWithdrawableBy(alice), 0);
    }

    function test_RejectsInvalidConfiguration() public {
        address mi = address(new HeadlineMarket());
        address fi = address(new FPMM());
        vm.expectRevert("Factory: missing fee recipient");
        new MarketFactory(ct, verifier, mi, fi, ILLMJudge(address(0)), 1e16, address(0));
        vm.expectRevert("Factory: protocol fee above 5%");
        new MarketFactory(ct, verifier, mi, fi, ILLMJudge(address(0)), 5e16 + 1, treasury);
        MarketFactory.CreateMarketParams memory p = defaultParams();
        p.fee = 99e16;
        vm.expectRevert("FPMM: fee must be < 100%");
        factory.createMarket(p);
    }

    function testFuzz_BuyConservesFees(uint96 amount) public {
        uint256 gross = bound(uint256(amount), 1, 100_000e6);
        vm.startPrank(bob);
        usdc.approve(address(pool), gross);
        pool.buy(gross, 0, 0);
        vm.stopPrank();
        assertEq(usdc.balanceOf(address(pool)), gross * 3e16 / 1e18);
        assertEq(pool.protocolFeesAccrued(), gross * 1e16 / 1e18);
        assertGe(usdc.balanceOf(address(pool)), pool.protocolFeesAccrued() + pool.feesWithdrawableBy(alice));
    }
}
