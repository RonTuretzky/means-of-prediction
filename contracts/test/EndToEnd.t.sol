// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {MarketTestBase} from "./MarketTestBase.sol";
import {HeadlineMarket} from "../src/market/HeadlineMarket.sol";
import {MarketFactory} from "../src/market/MarketFactory.sol";
import {FPMM} from "../src/market/FPMM.sol";
import {EmailProof} from "../src/dkim/IDKIMVerifier.sol";
import {ERC20} from "../src/tokens/ERC20.sol";

contract TestUSDCLike is ERC20 {
    constructor() ERC20("Test DAI", "DAI", 18) {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}

/// @notice Full lifecycle: permissionless market creation -> trading -> permissionless
/// DKIM settlement -> redemption. Mirrors the Playwright e2e flows.
contract EndToEndTest is MarketTestBase {
    function test_FullLifecycle_YesResolution() public {
        // 1. Alice permissionlessly opens a market with 10k USDC liquidity, 2-of-3 sources.
        (HeadlineMarket market, FPMM fpmm) = createFundedMarket(10_000e6);

        // 2. Bob believes YES: buys 2,000 USDC of YES.
        vm.startPrank(bob);
        usdc.approve(address(fpmm), 2000e6);
        uint256 bobYes = fpmm.buy(2000e6, 0, 0);
        vm.stopPrank();

        // 3. Carol believes NO: buys 1,000 USDC of NO.
        vm.startPrank(carol);
        usdc.approve(address(fpmm), 1000e6);
        uint256 carolNo = fpmm.buy(1000e6, 1, 0);
        vm.stopPrank();

        assertGt(fpmm.marginalPrice(0), 0.5e18); // YES demand outweighs NO

        // 4. The news breaks. A settler (neither trader nor creator) submits proofs of
        //    NYT and Reuters alert emails. Second accepted proof hits the threshold.
        vm.warp(block.timestamp + 3 days);
        EmailProof memory nyt = makeProof(
            "nytimes.com",
            block.timestamp - 1 hours,
            "nytdirect@nytimes.com",
            "Breaking News: Fed cuts rates by 50 basis points in emergency move",
            "The Federal Reserve cut its benchmark rate...",
            keccak256("nyt-email")
        );
        EmailProof memory reuters = makeProof(
            "email.reuters.com",
            block.timestamp - 30 minutes,
            "newsletters@email.reuters.com",
            "BREAKING: Fed slashes rates",
            "",
            keccak256("reuters-email")
        );
        vm.prank(settler);
        market.submitProof(0, nyt);
        assertEq(uint256(market.resolution()), uint256(HeadlineMarket.Resolution.Unresolved));
        vm.prank(settler);
        market.submitProof(2, reuters);
        assertEq(uint256(market.resolution()), uint256(HeadlineMarket.Resolution.Yes));

        // 5. Bob redeems YES at $1.00/share; Carol's NO redeems to zero.
        uint256[] memory sets = new uint256[](2);
        sets[0] = 1;
        sets[1] = 2;
        bytes32 conditionId = market.conditionId(); // hoisted: external call must not eat the prank

        uint256 bobBefore = usdc.balanceOf(bob);
        vm.prank(bob);
        ct.redeemPositions(usdc, conditionId, sets);
        assertEq(usdc.balanceOf(bob) - bobBefore, bobYes);

        uint256 carolBefore = usdc.balanceOf(carol);
        vm.prank(carol);
        ct.redeemPositions(usdc, conditionId, sets);
        assertEq(usdc.balanceOf(carol), carolBefore); // NO pays nothing
        assertEq(ct.balanceOf(fpmm.noPositionId(), carol), 0); // but shares burned

        // 6. Alice (LP) exits: fees + proportional pool tokens, then redeems.
        vm.startPrank(alice);
        fpmm.removeFunding(fpmm.balanceOf(alice));
        ct.redeemPositions(usdc, conditionId, sets);
        vm.stopPrank();

        // 7. Conservation: every USDC that entered has a home; contracts hold only dust.
        assertLt(usdc.balanceOf(address(ct)), 3);
        assertLt(usdc.balanceOf(address(fpmm)), 3);
        uint256 totalHeld = usdc.balanceOf(alice) + usdc.balanceOf(bob) + usdc.balanceOf(carol);
        assertApproxEqAbs(totalHeld, 3_000_000e6, 3); // three faucets of 1M each, redistributed
    }

    function test_FullLifecycle_NoResolution() public {
        (HeadlineMarket market, FPMM fpmm) = createFundedMarket(10_000e6);

        vm.startPrank(bob);
        usdc.approve(address(fpmm), 2000e6);
        fpmm.buy(2000e6, 0, 0); // bob bets YES... and the news never comes
        vm.stopPrank();

        vm.startPrank(carol);
        usdc.approve(address(fpmm), 1000e6);
        uint256 carolNo = fpmm.buy(1000e6, 1, 0);
        vm.stopPrank();

        // Deadline + buffer passes with no matching emails; anyone resolves NO.
        vm.warp(uint256(market.deadline()) + uint256(market.resolutionBuffer()) + 1);
        vm.prank(settler);
        market.resolveNo();

        uint256[] memory sets = new uint256[](2);
        sets[0] = 1;
        sets[1] = 2;
        bytes32 conditionId = market.conditionId();

        uint256 carolBefore = usdc.balanceOf(carol);
        vm.prank(carol);
        ct.redeemPositions(usdc, conditionId, sets);
        assertEq(usdc.balanceOf(carol) - carolBefore, carolNo); // NO pays $1.00

        uint256 bobBefore = usdc.balanceOf(bob);
        vm.prank(bob);
        ct.redeemPositions(usdc, conditionId, sets);
        assertEq(usdc.balanceOf(bob), bobBefore); // YES worthless
    }

    function test_CustomCollateralToken() public {
        // "configurable market token management": open a market in a bespoke ERC20
        vm.startPrank(bob);
        MarketFactory.CreateMarketParams memory p = defaultParams();
        TestUSDCLike dai = new TestUSDCLike();
        dai.mint(bob, 1_000e18);
        p.collateralToken = dai;
        p.initialLiquidity = 500e18;
        dai.approve(address(factory), 500e18);
        (HeadlineMarket market, FPMM fpmm) = factory.createMarket(p);
        vm.stopPrank();

        assertEq(address(fpmm.collateralToken()), address(dai));
        (uint256 yesBal,) = fpmm.poolBalances();
        assertEq(yesBal, 500e18);

        // trade in the custom token
        vm.startPrank(bob);
        dai.approve(address(fpmm), 100e18);
        uint256 bought = fpmm.buy(100e18, 0, 0);
        vm.stopPrank();
        assertGt(bought, 0);
        assertEq(ct.balanceOf(market.yesPositionId(), bob), bought);
    }
}
