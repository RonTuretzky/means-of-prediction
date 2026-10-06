// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {MarketTestBase} from "./MarketTestBase.sol";
import {MarketFactory} from "../src/market/MarketFactory.sol";
import {HeadlineMarket} from "../src/market/HeadlineMarket.sol";
import {FPMM} from "../src/market/FPMM.sol";
import {ERC20} from "../src/tokens/ERC20.sol";
import {Clones} from "../src/utils/Clones.sol";

contract FeeCollateral is ERC20 {
    address public failedRecipient;

    constructor(uint8 precision) ERC20("Fee test collateral", "FEE", precision) {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }

    function failTransfersTo(address recipient) external {
        failedRecipient = recipient;
    }

    function transfer(address to, uint256 amount) public override returns (bool) {
        if (to == failedRecipient) return false;
        return super.transfer(to, amount);
    }
}

/// @dev Run the same accounting, rounding and lifecycle checks with both collateral precisions.
abstract contract ProtocolFeesTestBase is MarketTestBase {
    uint256 constant ONE = 1e18;
    uint256 constant LP_FEE = 2e16;
    uint256 constant OPERATOR_FEE = 22e15;
    uint256 constant TOTAL_FEE = LP_FEE + OPERATOR_FEE;
    address treasury = makeAddr("operator treasury");
    FeeCollateral token;
    FPMM pool;
    uint256 unit;

    function collateralDecimals() internal pure virtual returns (uint8);

    function setUp() public override {
        super.setUp();
        unit = 10 ** collateralDecimals();
        token = new FeeCollateral(collateralDecimals());
        token.mint(alice, 1_000_000 * unit);
        token.mint(bob, 1_000_000 * unit);
        token.mint(carol, 1_000_000 * unit);
        factory = newFactory(OPERATOR_FEE, treasury);
        pool = createPool(factory, LP_FEE, 10_000 * unit);
    }

    function newFactory(uint256 rate, address recipient) internal returns (MarketFactory) {
        return new MarketFactory(ct, verifier, address(new HeadlineMarket()), address(new FPMM()), rate, recipient);
    }

    function createPool(MarketFactory f, uint256 lpFee, uint256 liquidity) internal returns (FPMM result) {
        MarketFactory.CreateMarketParams memory p = defaultParams();
        p.collateralToken = token;
        p.fee = lpFee;
        p.initialLiquidity = liquidity;
        vm.startPrank(alice);
        token.approve(address(f), liquidity);
        (, result) = f.createMarket(p);
        vm.stopPrank();
    }

    function buy(FPMM f, uint256 gross, uint256 outcome) internal returns (uint256 bought) {
        uint256 quote = f.calcBuyAmount(gross, outcome);
        vm.startPrank(bob);
        token.approve(address(f), gross);
        bought = f.buy(gross, outcome, quote);
        vm.stopPrank();
        assertEq(bought, quote, "buy quote/execution parity");
    }

    function sell(FPMM f, uint256 net, uint256 outcome) internal returns (uint256 sold) {
        uint256 quote = f.calcSellAmount(net, outcome);
        uint256 balance = token.balanceOf(bob);
        vm.startPrank(bob);
        ct.setApprovalForAll(address(f), true);
        sold = f.sell(net, outcome, quote);
        vm.stopPrank();
        assertEq(sold, quote, "sell quote/execution parity");
        assertEq(token.balanceOf(bob) - balance, net, "exact net collateral return");
    }

    function ceilDiv(uint256 n, uint256 d) internal pure returns (uint256) {
        return n == 0 ? 0 : (n - 1) / d + 1;
    }

    function assertBacked(FPMM f) internal view {
        uint256 lpClaims = f.feesWithdrawableBy(alice) + f.feesWithdrawableBy(bob) + f.feesWithdrawableBy(carol);
        assertGe(token.balanceOf(address(f)), f.protocolFeesAccrued() + lpClaims, "fee liabilities are backed");
    }

    function test_FactoryRateAndRecipientInheritedIndependently() public {
        assertEq(factory.protocolFee(), OPERATOR_FEE);
        assertEq(factory.feeRecipient(), treasury);
        assertEq(pool.fee(), LP_FEE);
        assertEq(pool.protocolFee(), OPERATOR_FEE);
        assertEq(pool.totalFee(), TOTAL_FEE);
        assertEq(pool.feeRecipient(), treasury);
        FPMM noLPFee = createPool(factory, 0, 1_000 * unit);
        assertEq(noLPFee.fee(), 0);
        assertEq(noLPFee.protocolFee(), OPERATOR_FEE);
        assertEq(noLPFee.feeRecipient(), treasury);
    }

    function test_BuySeparatesOperatorAndLPFeesFromSameGross() public {
        uint256 before = token.balanceOf(bob);
        buy(pool, 1_000 * unit, 0);
        assertEq(before - token.balanceOf(bob), 1_000 * unit);
        assertEq(pool.protocolFeesAccrued(), 22 * unit);
        assertEq(pool.feesWithdrawableBy(alice), 20 * unit);
        assertEq(token.balanceOf(address(pool)), 42 * unit);
        assertEq(token.balanceOf(address(ct)), 10_958 * unit);
        assertBacked(pool);
    }

    function test_SellUsesCeilingGrossAndSameFeeBasis() public {
        buy(pool, 1_000 * unit, 1);
        uint256 net = 500 * unit + 1;
        uint256 gross = ceilDiv(net * ONE, ONE - TOTAL_FEE);
        uint256 protocolBefore = pool.protocolFeesAccrued();
        uint256 cashBefore = token.balanceOf(address(pool));
        (uint256 y0, uint256 n0) = pool.poolBalances();
        sell(pool, net, 1);
        (uint256 y1, uint256 n1) = pool.poolBalances();
        assertGe(y1 * n1, y0 * n0, "constant product preserved on sell");
        assertEq(pool.protocolFeesAccrued() - protocolBefore, gross * OPERATOR_FEE / ONE);
        assertEq(token.balanceOf(address(pool)) - cashBefore, gross - net);
        assertEq(token.balanceOf(address(ct)), 10_958 * unit - gross);
        assertBacked(pool);
    }

    function test_TinyTradesHaveDeterministicRounding() public {
        FPMM tiny = createPool(factory, LP_FEE, 1_000);
        buy(tiny, 1, 0); // floor(1 * 4.2%) == 0
        assertEq(tiny.protocolFeesAccrued(), 0);
        assertEq(token.balanceOf(address(tiny)), 0);
        buy(tiny, 24, 0); // total = 1, operator = 0, remainder = LP
        assertEq(tiny.protocolFeesAccrued(), 0);
        assertEq(tiny.feesWithdrawableBy(alice), 1);
        sell(tiny, 1, 0); // ceil(1 / .958) == 2, total = 1, operator = 0
        assertEq(token.balanceOf(address(tiny)), 2);
        assertEq(tiny.protocolFeesAccrued(), 0);
        assertEq(tiny.feesWithdrawableBy(alice), 2);
        assertBacked(tiny);
    }

    function test_WithdrawOperatorThenLPAndRepeatedCalls() public {
        buy(pool, 1_000 * unit, 0);
        uint256 lpBalance = token.balanceOf(alice);
        uint256 callerBalance = token.balanceOf(carol);
        vm.prank(carol);
        pool.withdrawProtocolFees();
        assertEq(token.balanceOf(treasury), 22 * unit);
        assertEq(token.balanceOf(carol), callerBalance, "caller cannot redirect treasury fees");
        assertEq(pool.protocolFeesAccrued(), 0);
        assertEq(pool.feesWithdrawableBy(alice), 20 * unit);
        pool.withdrawProtocolFees();
        pool.withdrawFees(alice);
        pool.withdrawFees(alice);
        assertEq(token.balanceOf(alice) - lpBalance, 20 * unit);
        assertEq(token.balanceOf(address(pool)), 0);
        assertEq(token.balanceOf(treasury), 22 * unit);
    }

    function test_WithdrawLPThenOperatorAndAccrueAgain() public {
        buy(pool, 1_000 * unit, 0);
        pool.withdrawFees(alice);
        assertEq(token.balanceOf(address(pool)), 22 * unit);
        assertEq(pool.protocolFeesAccrued(), 22 * unit);
        pool.withdrawProtocolFees();
        buy(pool, 500 * unit, 1);
        assertEq(pool.protocolFeesAccrued(), 11 * unit);
        assertEq(pool.feesWithdrawableBy(alice), 10 * unit);
        pool.withdrawProtocolFees();
        pool.withdrawFees(alice);
        assertEq(token.balanceOf(treasury), 33 * unit);
        assertEq(token.balanceOf(address(pool)), 0);
    }

    function test_FailedOperatorTransferRestoresAccrual() public {
        buy(pool, 1_000 * unit, 0);
        token.failTransfersTo(treasury);
        vm.expectRevert("FPMM: transfer failed");
        pool.withdrawProtocolFees();
        assertEq(pool.protocolFeesAccrued(), 22 * unit);
        assertEq(token.balanceOf(address(pool)), 42 * unit);
        assertEq(token.balanceOf(treasury), 0);
        token.failTransfersTo(address(0));
        pool.withdrawProtocolFees();
        assertEq(token.balanceOf(treasury), 22 * unit);
    }

    function test_FailedLPTransferDoesNotTouchOperatorAccrual() public {
        buy(pool, 1_000 * unit, 0);
        token.failTransfersTo(alice);
        vm.expectRevert("FPMM: transfer failed");
        pool.withdrawFees(alice);
        assertEq(pool.feesWithdrawableBy(alice), 20 * unit);
        assertEq(pool.protocolFeesAccrued(), 22 * unit);
        pool.withdrawProtocolFees();
        token.failTransfersTo(address(0));
        pool.withdrawFees(alice);
        assertEq(token.balanceOf(address(pool)), 0);
    }

    function test_LPTransfersPreservePastFeesAndSplitFutureFees() public {
        buy(pool, 1_000 * unit, 0);
        uint256 half = pool.balanceOf(alice) / 2;
        vm.prank(alice);
        pool.transfer(carol, half);
        assertEq(pool.feesWithdrawableBy(alice), 20 * unit);
        assertEq(pool.feesWithdrawableBy(carol), 0);
        buy(pool, 1_000 * unit, 1);
        assertEq(pool.feesWithdrawableBy(alice), 30 * unit);
        assertEq(pool.feesWithdrawableBy(carol), 10 * unit);
        assertEq(pool.protocolFeesAccrued(), 44 * unit);
        pool.withdrawFees(carol);
        pool.withdrawProtocolFees();
        pool.withdrawFees(alice);
        assertEq(token.balanceOf(address(pool)), 0);
    }

    function test_FractionalLPFeesStayWithTransferor() public {
        FPMM f = createPool(factory, LP_FEE, 1_000);
        vm.prank(alice);
        f.transfer(carol, 500);
        buy(f, 24, 0); // one LP fee atom: each holder has an unwithdrawable half
        assertEq(f.feesWithdrawableBy(alice), 0);
        assertEq(f.feesWithdrawableBy(carol), 0);
        vm.prank(carol);
        f.transfer(bob, 250); // carol retains her accrued half, including its fraction
        buy(f, 24, 1);
        buy(f, 24, 0);
        assertEq(f.feesWithdrawableBy(alice), 1); // 1.5 atoms accrued
        assertEq(f.feesWithdrawableBy(carol), 1); // .5 + .25 + .25
        assertEq(f.feesWithdrawableBy(bob), 0); // .25 + .25
        f.withdrawFees(alice);
        f.withdrawFees(carol);
        assertBacked(f);
    }

    function test_MintBurnAndExitDoNotConsumeOperatorFees() public {
        buy(pool, 1_000 * unit, 0);
        vm.startPrank(carol);
        token.approve(address(pool), 5_000 * unit);
        pool.addFunding(5_000 * unit, new uint256[](0), carol);
        vm.stopPrank();
        assertEq(pool.feesWithdrawableBy(carol), 0);
        assertEq(pool.feesWithdrawableBy(alice), 20 * unit);
        assertEq(pool.protocolFeesAccrued(), 22 * unit);
        buy(pool, 1_000 * unit, 1);
        assertBacked(pool);
        uint256 aliceShares = pool.balanceOf(alice);
        uint256 carolShares = pool.balanceOf(carol);
        vm.prank(alice);
        pool.removeFunding(aliceShares);
        assertBacked(pool);
        vm.prank(carol);
        pool.removeFunding(carolShares);
        assertEq(pool.totalSupply(), 0);
        assertEq(pool.protocolFeesAccrued(), 44 * unit);
        pool.withdrawFees(alice);
        pool.withdrawFees(carol);
        assertGe(token.balanceOf(address(pool)), 44 * unit);
        pool.withdrawProtocolFees();
        assertEq(token.balanceOf(treasury), 44 * unit);
        // Only bounded accumulator/share rounding dust may remain.
        assertLe(token.balanceOf(address(pool)), 2 + 2 * (15_000 * unit / ONE));
    }

    function test_RepeatedSmallMintsCannotDiluteFeeBuckets() public {
        FPMM f = createPool(factory, LP_FEE, 1_000);
        buy(f, 1_000, 0);
        f.withdrawFees(alice);
        vm.startPrank(carol);
        token.approve(address(f), 1_000);
        for (uint256 i = 0; i < 100; ++i) {
            f.addFunding(2, new uint256[](0), carol);
        }
        vm.stopPrank();
        assertEq(f.feesWithdrawableBy(carol), 0, "new shares cannot claim already-earned fees");
        assertBacked(f);
        f.withdrawFees(carol);
        f.withdrawProtocolFees();
        assertEq(token.balanceOf(treasury), 22);
    }

    function test_WithdrawalAndLPExitRemainAvailableAfterResolution() public {
        buy(pool, 1_000 * unit, 0);
        HeadlineMarket market = HeadlineMarket(factory.getMarket(0).market);
        vm.warp(uint256(market.deadline()) + uint256(market.resolutionBuffer()) + 1);
        market.resolveNo();
        vm.expectRevert("FPMM: market resolved");
        pool.buy(1, 0, 0);
        uint256 shares = pool.balanceOf(alice);
        vm.prank(alice);
        pool.removeFunding(shares);
        assertEq(pool.protocolFeesAccrued(), 22 * unit);
        assertEq(token.balanceOf(address(pool)), 22 * unit);
        pool.withdrawProtocolFees();
        pool.withdrawProtocolFees();
        assertEq(token.balanceOf(treasury), 22 * unit);
        assertEq(token.balanceOf(address(pool)), 0);
    }

    function test_ZeroLPFeeSendsSellRoundingDustToOperator() public {
        FPMM f = createPool(factory, 0, 1_000);
        buy(f, 100, 0);
        assertEq(f.protocolFeesAccrued(), 2);
        assertEq(f.feesWithdrawableBy(alice), 0);
        sell(f, 1, 0); // gross = 2, operator floor = 0, all 1 fee atom belongs to operator
        assertEq(f.protocolFeesAccrued(), 3);
        assertEq(f.feesWithdrawableBy(alice), 0);
        assertEq(token.balanceOf(address(f)), 3);
        f.withdrawProtocolFees();
        assertEq(token.balanceOf(address(f)), 0);
    }

    function test_ZeroOperatorFeePreservesLPOnlyBehavior() public {
        FPMM f = createPool(newFactory(0, address(0)), LP_FEE, 1_000 * unit);
        buy(f, 100 * unit, 0);
        sell(f, 40 * unit, 0);
        assertEq(f.protocolFeesAccrued(), 0);
        assertEq(f.totalFee(), LP_FEE);
        assertGt(f.feesWithdrawableBy(alice), 2 * unit);
        f.withdrawProtocolFees();
        assertBacked(f);
    }

    function test_ZeroBothFeesHasNoAccrual() public {
        FPMM f = createPool(newFactory(0, address(0)), 0, 1_000 * unit);
        buy(f, 100 * unit + 1, 0);
        sell(f, 40 * unit + 1, 0);
        assertEq(f.protocolFeesAccrued(), 0);
        assertEq(f.feesWithdrawableBy(alice), 0);
        assertEq(token.balanceOf(address(f)), 0);
        f.withdrawProtocolFees();
        f.withdrawFees(alice);
    }

    function test_ProtocolFeeCapAndRecipientValidation() public {
        address marketImplementation = address(new HeadlineMarket());
        address poolImplementation = address(new FPMM());
        vm.expectRevert("Factory: missing fee recipient");
        new MarketFactory(ct, verifier, marketImplementation, poolImplementation, OPERATOR_FEE, address(0));
        vm.expectRevert("Factory: protocol fee above 5%");
        new MarketFactory(ct, verifier, marketImplementation, poolImplementation, 5e16 + 1, treasury);
        MarketFactory capped = newFactory(5e16, treasury);
        assertEq(capped.protocolFee(), 5e16);
        assertEq(createPool(capped, LP_FEE, 1_000 * unit).totalFee(), 7e16);
    }

    function test_CombinedFeeMustStayStrictlyBelowOne() public {
        MarketFactory.CreateMarketParams memory p = defaultParams();
        p.fee = ONE - OPERATOR_FEE;
        vm.expectRevert("FPMM: fee must be < 100%");
        factory.createMarket(p);
        p.fee = ONE;
        vm.expectRevert("FPMM: fee must be < 100%");
        factory.createMarket(p);
        p.fee = type(uint256).max;
        vm.expectRevert("FPMM: fee must be < 100%");
        factory.createMarket(p);
        p.fee = ONE - OPERATOR_FEE - 1;
        (, FPMM f) = factory.createMarket(p);
        assertEq(f.totalFee(), ONE - 1);
    }

    function test_PoolInitializeRejectsMissingRecipientAndReinitialization() public {
        FPMM implementation = new FPMM();
        FPMM clone = FPMM(Clones.clone(address(implementation)));
        bytes32 condition = pool.conditionId();
        vm.expectRevert("FPMM: missing fee recipient");
        clone.initialize(ct, token, condition, LP_FEE, OPERATOR_FEE, address(0));
        clone.initialize(ct, token, condition, LP_FEE, OPERATOR_FEE, treasury);
        vm.expectRevert("FPMM: already initialized");
        clone.initialize(ct, token, condition, 0, 0, bob);
        vm.expectRevert("FPMM: already initialized");
        implementation.initialize(ct, token, condition, 0, 0, bob);
        assertEq(clone.feeRecipient(), treasury);
        assertEq(clone.protocolFee(), OPERATOR_FEE);
    }

    function test_RevertedTradesDoNotAccrueFees() public {
        uint256 amount = 100 * unit;
        uint256 quote = pool.calcBuyAmount(amount, 0);
        vm.startPrank(bob);
        token.approve(address(pool), amount);
        vm.expectRevert("FPMM: max slippage exceeded");
        pool.buy(amount, 0, quote + 1);
        vm.stopPrank();
        assertEq(pool.protocolFeesAccrued(), 0);
        assertEq(token.balanceOf(address(pool)), 0);
        buy(pool, amount, 0);
        quote = pool.calcSellAmount(10 * unit, 0);
        vm.startPrank(bob);
        ct.setApprovalForAll(address(pool), true);
        vm.expectRevert("FPMM: max slippage exceeded");
        pool.sell(10 * unit, 0, quote - 1);
        vm.stopPrank();
        assertEq(pool.protocolFeesAccrued(), amount * OPERATOR_FEE / ONE);
        assertEq(token.balanceOf(address(pool)), amount * TOTAL_FEE / ONE);
    }

    function testFuzz_MintBurnTransferWithdrawalSequence(uint256 seed) public {
        FPMM f = createPool(factory, LP_FEE, 1_000);
        uint256 lpAllocated;
        uint256 operatorAllocated;
        address[3] memory holders = [alice, bob, carol];
        for (uint256 i = 0; i < 36; ++i) {
            seed = uint256(keccak256(abi.encode(seed, i)));
            address holder = holders[seed % holders.length];
            uint256 action = i % 6;
            if (action == 0) {
                uint256 gross = 24 + seed % 977;
                buy(f, gross, (seed >> 8) % 2);
                uint256 operatorAmount = gross * OPERATOR_FEE / ONE;
                lpAllocated += gross * TOTAL_FEE / ONE - operatorAmount;
                operatorAllocated += operatorAmount;
            } else if (action == 1) {
                uint256 funds = 1 + seed % 101;
                vm.startPrank(holder);
                token.approve(address(f), funds);
                f.addFunding(funds, new uint256[](0), holder);
                vm.stopPrank();
            } else if (action == 2) {
                uint256 balance = f.balanceOf(holder);
                if (balance > 0) {
                    address receiver = holders[(seed % holders.length + 1) % holders.length];
                    vm.prank(holder);
                    f.transfer(receiver, 1 + (seed >> 16) % balance);
                }
            } else if (action == 3) {
                uint256 balance = f.balanceOf(holder);
                if (balance > 0) {
                    uint256 shares = 1 + (seed >> 16) % balance;
                    if (shares == f.totalSupply()) --shares; // keep the market funded for later trades
                    vm.prank(holder);
                    f.removeFunding(shares);
                }
            } else if (action == 4) {
                f.withdrawFees(holder);
            } else {
                f.withdrawProtocolFees();
            }
            uint256 paid;
            uint256 claims;
            for (uint256 j = 0; j < holders.length; ++j) {
                paid += f.feesWithdrawn(holders[j]);
                claims += f.feesWithdrawableBy(holders[j]);
            }
            assertLe(paid + claims, lpAllocated, "LP paid and owed never exceed the LP allocation");
            assertEq(token.balanceOf(treasury) + f.protocolFeesAccrued(), operatorAllocated);
            assertBacked(f);
            // Exercise withdrawal interleavings after every mint, burn and transfer.
            for (uint256 j = 0; j < holders.length; ++j) {
                f.withdrawFees(holders[j]);
            }
            assertBacked(f);
        }
        f.withdrawProtocolFees();
        assertEq(token.balanceOf(treasury), operatorAllocated);
    }

    function testFuzz_BuyQuoteFeeConservation(uint96 raw, bool noOutcome) public {
        uint256 gross = bound(uint256(raw), 1, 100_000 * unit);
        (uint256 y0, uint256 n0) = pool.poolBalances();
        buy(pool, gross, noOutcome ? 1 : 0);
        (uint256 y1, uint256 n1) = pool.poolBalances();
        assertGe(y1 * n1, y0 * n0);
        assertEq(token.balanceOf(address(pool)), gross * TOTAL_FEE / ONE);
        assertEq(pool.protocolFeesAccrued(), gross * OPERATOR_FEE / ONE);
        assertBacked(pool);
        pool.withdrawFees(alice);
        pool.withdrawProtocolFees();
        assertEq(token.balanceOf(treasury), gross * OPERATOR_FEE / ONE);
        assertLe(token.balanceOf(address(pool)), 1 + 10_000 * unit / ONE);
    }

    function testFuzz_SellQuoteFeeConservation(uint96 raw, bool noOutcome) public {
        uint256 outcome = noOutcome ? 1 : 0;
        buy(pool, 1_000 * unit, outcome);
        uint256 net = bound(uint256(raw), 1, 500 * unit);
        uint256 gross = ceilDiv(net * ONE, ONE - TOTAL_FEE);
        sell(pool, net, outcome);
        assertEq(pool.protocolFeesAccrued(), 22 * unit + gross * OPERATOR_FEE / ONE);
        assertEq(token.balanceOf(address(pool)), 42 * unit + gross - net);
        assertBacked(pool);
        pool.withdrawProtocolFees();
        pool.withdrawFees(alice);
        assertLe(token.balanceOf(address(pool)), 1 + 10_000 * unit / ONE);
    }

    function testFuzz_ShareMovesCannotSpendOperatorFees(uint96 raw, uint96 transferRaw) public {
        uint256 gross = bound(uint256(raw), 24, 1_000 * unit);
        buy(pool, gross, 0);
        uint256 shares = bound(uint256(transferRaw), 1, pool.balanceOf(alice));
        pool.withdrawFees(alice);
        vm.prank(alice);
        pool.transfer(carol, shares);
        assertBacked(pool);
        pool.withdrawFees(carol);
        pool.withdrawFees(alice);
        vm.prank(carol);
        pool.transfer(alice, shares);
        pool.withdrawFees(alice);
        assertBacked(pool);
        pool.withdrawProtocolFees();
        assertEq(token.balanceOf(treasury), gross * OPERATOR_FEE / ONE);
    }
}

contract ProtocolFees6DecimalsTest is ProtocolFeesTestBase {
    function collateralDecimals() internal pure override returns (uint8) {
        return 6;
    }
}

contract ProtocolFees18DecimalsTest is ProtocolFeesTestBase {
    function collateralDecimals() internal pure override returns (uint8) {
        return 18;
    }
}
