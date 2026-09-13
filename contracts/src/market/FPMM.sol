// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ERC20, IERC20} from "../tokens/ERC20.sol";
import {IERC1155Receiver} from "../tokens/ERC1155.sol";
import {ConditionalTokens} from "../tokens/ConditionalTokens.sol";

/// @title FPMM — Fixed Product Market Maker
/// @notice Binary-outcome AMM over ConditionalTokens positions, modelled on the Gnosis
/// FixedProductMarketMaker that powered Polymarket's original trading experience
/// (Polymarket later moved to an offchain orderbook — see the backlog). Holds YES/NO
/// outcome tokens; the product of the pool balances is kept constant across trades.
///
///   - `addFunding` locks collateral, splits it into complete sets and mints LP shares.
///     Initial funding may pass a `distributionHint` to set the starting odds.
///   - `buy` splits collateral into complete sets and pays out the bought outcome.
///   - `sell` pulls outcome tokens, merges complete sets back into collateral.
///   - Trading fees (set at creation, 1e18-scale) accrue in collateral to LP shares,
///     claimable via `withdrawFees` (accumulator-per-share accounting).
///
/// Prices: marginal price of outcome i = oppositeBalance / (yesBalance + noBalance),
/// i.e. a 0..1 probability — displayed as cents in the UI, Polymarket-style.
contract FPMM is ERC20, IERC1155Receiver {
    uint256 public constant ONE = 1e18;

    event FundingAdded(address indexed funder, uint256 amountAdded, uint256 sharesMinted);
    event FundingRemoved(address indexed funder, uint256 yesAmount, uint256 noAmount, uint256 sharesBurnt);
    event Buy(
        address indexed buyer, uint256 investmentAmount, uint256 feeAmount, uint256 outcomeIndex, uint256 tokensBought
    );
    event Sell(
        address indexed seller, uint256 returnAmount, uint256 feeAmount, uint256 outcomeIndex, uint256 tokensSold
    );
    event FeesWithdrawn(address indexed funder, uint256 amount);
    event ProtocolFeesAccrued(uint256 amount);
    event ProtocolFeesWithdrawn(address indexed recipient, uint256 amount);

    // Storage (not immutable): FPMMs are EIP-1167 clones of one implementation.
    ConditionalTokens public conditionalTokens;
    IERC20 public collateralToken;
    bytes32 public conditionId;
    uint256 public fee; // fraction of each trade, 1e18-scale (2e16 = 2%)
    uint256 public protocolFee; // platform rate, additional to the LP fee
    address public feeRecipient; // fixed for the lifetime of this pool
    uint256 public protocolFeesAccrued;
    uint256 public yesPositionId;
    uint256 public noPositionId;
    bool private initialized;

    // Fee accounting: accumulated collateral fees per LP share (1e18-scaled), with
    // signed corrections so mints/burns/transfers preserve accrued entitlements.
    uint256 public accFeesPerShare;
    mapping(address => int256) private feeCorrection;
    mapping(address => uint256) public feesWithdrawn;

    /// @dev Locks the shared implementation; `decimals` (immutable, 18) is baked into
    /// the implementation bytecode and therefore shared by every clone — correct,
    /// since all LP shares use it.
    constructor() ERC20("Headline Market LP", "HMLP", 18) {
        initialized = true;
    }

    function initialize(ConditionalTokens _conditionalTokens, IERC20 _collateralToken, bytes32 _conditionId, uint256 _fee,
        uint256 _protocolFee, address _feeRecipient)
        external
    {
        require(!initialized, "FPMM: already initialized");
        initialized = true;
        require(_fee < ONE && _protocolFee < ONE - _fee, "FPMM: fee must be < 100%");
        require(_protocolFee == 0 || _feeRecipient != address(0), "FPMM: missing fee recipient");
        require(_conditionalTokens.getOutcomeSlotCount(_conditionId) == 2, "FPMM: binary conditions only");
        name = "Headline Market LP";
        symbol = "HMLP";
        conditionalTokens = _conditionalTokens;
        collateralToken = _collateralToken;
        conditionId = _conditionId;
        fee = _fee;
        protocolFee = _protocolFee;
        feeRecipient = _feeRecipient;
        yesPositionId =
            _conditionalTokens.getPositionId(_collateralToken, _conditionalTokens.getCollectionId(_conditionId, 1));
        noPositionId =
            _conditionalTokens.getPositionId(_collateralToken, _conditionalTokens.getCollectionId(_conditionId, 2));
    }

    modifier whileTrading() {
        require(conditionalTokens.payoutDenominator(conditionId) == 0, "FPMM: market resolved");
        _;
    }

    // ------------------------------------------------------------------
    // Liquidity
    // ------------------------------------------------------------------

    /// @param distributionHint Only on initial funding: desired pool balance ratio,
    /// e.g. [3, 1] keeps 3:1 YES:NO in the pool (25% starting YES price) and returns
    /// the surplus outcome tokens to `receiver`. Empty for 50/50 or follow-on funding.
    /// @param receiver Gets the LP shares and any surplus outcome tokens (lets the
    /// factory fund on behalf of the market creator).
    function addFunding(uint256 addedFunds, uint256[] calldata distributionHint, address receiver)
        external
        whileTrading
        returns (uint256 mintAmount)
    {
        require(addedFunds > 0, "FPMM: no funds added");
        uint256[2] memory sendBack;

        if (totalSupply == 0) {
            mintAmount = addedFunds;
            if (distributionHint.length > 0) {
                require(distributionHint.length == 2, "FPMM: hint must have 2 entries");
                uint256 maxHint =
                    distributionHint[0] > distributionHint[1] ? distributionHint[0] : distributionHint[1];
                require(maxHint > 0, "FPMM: bad hint");
                sendBack[0] = addedFunds - (addedFunds * distributionHint[0]) / maxHint;
                sendBack[1] = addedFunds - (addedFunds * distributionHint[1]) / maxHint;
            }
        } else {
            require(distributionHint.length == 0, "FPMM: hint only on initial funding");
            (uint256 yesBal, uint256 noBal) = poolBalances();
            uint256 maxBal = yesBal > noBal ? yesBal : noBal;
            sendBack[0] = addedFunds - (addedFunds * yesBal) / maxBal;
            sendBack[1] = addedFunds - (addedFunds * noBal) / maxBal;
            mintAmount = (addedFunds * totalSupply) / maxBal;
        }

        require(collateralToken.transferFrom(msg.sender, address(this), addedFunds), "FPMM: transfer failed");
        collateralToken.approve(address(conditionalTokens), addedFunds);
        conditionalTokens.splitPosition(collateralToken, conditionId, addedFunds);
        if (sendBack[0] > 0) {
            conditionalTokens.safeTransferFrom(address(this), receiver, yesPositionId, sendBack[0], "");
        }
        if (sendBack[1] > 0) {
            conditionalTokens.safeTransferFrom(address(this), receiver, noPositionId, sendBack[1], "");
        }
        _mint(receiver, mintAmount);
        emit FundingAdded(receiver, addedFunds, mintAmount);
    }

    /// @notice Burn LP shares for a proportional slice of both outcome-token pools
    /// (merge or redeem them separately). Accrued fees are paid out alongside.
    function removeFunding(uint256 sharesToBurn) external {
        withdrawFees(msg.sender);
        (uint256 yesBal, uint256 noBal) = poolBalances();
        uint256 yesOut = (yesBal * sharesToBurn) / totalSupply;
        uint256 noOut = (noBal * sharesToBurn) / totalSupply;
        _burn(msg.sender, sharesToBurn);
        if (yesOut > 0) conditionalTokens.safeTransferFrom(address(this), msg.sender, yesPositionId, yesOut, "");
        if (noOut > 0) conditionalTokens.safeTransferFrom(address(this), msg.sender, noPositionId, noOut, "");
        emit FundingRemoved(msg.sender, yesOut, noOut, sharesToBurn);
    }

    // ------------------------------------------------------------------
    // Trading
    // ------------------------------------------------------------------

    /// @notice Outcome tokens received for `investmentAmount` collateral, fee included.
    function calcBuyAmount(uint256 investmentAmount, uint256 outcomeIndex) public view returns (uint256) {
        require(outcomeIndex < 2, "FPMM: bad outcome index");
        uint256 invMinusFee = investmentAmount - (investmentAmount * totalFee()) / ONE;
        (uint256 yesBal, uint256 noBal) = poolBalances();
        (uint256 buyBal, uint256 otherBal) = outcomeIndex == 0 ? (yesBal, noBal) : (noBal, yesBal);
        require(buyBal > 0 && otherBal > 0, "FPMM: no liquidity");
        // Constant product: newBuyBal * (otherBal + invMinusFee) >= buyBal * otherBal
        uint256 newBuyBal = ceilDiv(buyBal * otherBal, otherBal + invMinusFee);
        return buyBal + invMinusFee - newBuyBal;
    }

    /// @notice Outcome tokens that must be sold to receive `returnAmount` collateral.
    function calcSellAmount(uint256 returnAmount, uint256 outcomeIndex) public view returns (uint256) {
        require(outcomeIndex < 2, "FPMM: bad outcome index");
        uint256 returnPlusFee = ceilDiv(returnAmount * ONE, ONE - totalFee());
        (uint256 yesBal, uint256 noBal) = poolBalances();
        (uint256 sellBal, uint256 otherBal) = outcomeIndex == 0 ? (yesBal, noBal) : (noBal, yesBal);
        require(sellBal > 0 && otherBal > returnPlusFee, "FPMM: insufficient liquidity");
        uint256 newSellBal = ceilDiv(sellBal * otherBal, otherBal - returnPlusFee);
        return returnPlusFee + newSellBal - sellBal;
    }

    /// @notice Buy `outcomeIndex` (0 = YES, 1 = NO) with `investmentAmount` collateral.
    function buy(uint256 investmentAmount, uint256 outcomeIndex, uint256 minOutcomeTokensToBuy)
        external
        whileTrading
        returns (uint256 tokensBought)
    {
        tokensBought = calcBuyAmount(investmentAmount, outcomeIndex);
        require(tokensBought >= minOutcomeTokensToBuy, "FPMM: max slippage exceeded");

        require(collateralToken.transferFrom(msg.sender, address(this), investmentAmount), "FPMM: transfer failed");
        uint256 feeAmount = (investmentAmount * totalFee()) / ONE;
        _collectTradeFees(investmentAmount, feeAmount);
        uint256 invMinusFee = investmentAmount - feeAmount;
        collateralToken.approve(address(conditionalTokens), invMinusFee);
        conditionalTokens.splitPosition(collateralToken, conditionId, invMinusFee);
        conditionalTokens.safeTransferFrom(
            address(this), msg.sender, outcomeIndex == 0 ? yesPositionId : noPositionId, tokensBought, ""
        );
        emit Buy(msg.sender, investmentAmount, feeAmount, outcomeIndex, tokensBought);
    }

    /// @notice Sell outcome tokens for exactly `returnAmount` collateral.
    /// Requires prior `setApprovalForAll(fpmm, true)` on ConditionalTokens.
    function sell(uint256 returnAmount, uint256 outcomeIndex, uint256 maxOutcomeTokensToSell)
        external
        whileTrading
        returns (uint256 tokensSold)
    {
        tokensSold = calcSellAmount(returnAmount, outcomeIndex);
        require(tokensSold <= maxOutcomeTokensToSell, "FPMM: max slippage exceeded");

        conditionalTokens.safeTransferFrom(
            msg.sender, address(this), outcomeIndex == 0 ? yesPositionId : noPositionId, tokensSold, ""
        );
        uint256 returnPlusFee = ceilDiv(returnAmount * ONE, ONE - totalFee());
        conditionalTokens.mergePositions(collateralToken, conditionId, returnPlusFee);
        _collectTradeFees(returnPlusFee, returnPlusFee - returnAmount);
        require(collateralToken.transfer(msg.sender, returnAmount), "FPMM: transfer failed");
        emit Sell(msg.sender, returnAmount, returnPlusFee - returnAmount, outcomeIndex, tokensSold);
    }

    // ------------------------------------------------------------------
    // Fees
    // ------------------------------------------------------------------

    function feesWithdrawableBy(address account) public view returns (uint256) {
        // Saturating: the accumulator's per-share floor rounding can leave
        // `entitledFees` a wei or two below `feesWithdrawn` after a share
        // mint/burn/transfer, which would otherwise underflow and brick an LP's
        // withdrawFees / removeFunding (and thus their exit).
        uint256 entitled = entitledFees(account);
        uint256 withdrawn = feesWithdrawn[account];
        return entitled > withdrawn ? entitled - withdrawn : 0;
    }

    function withdrawFees(address account) public {
        uint256 amount = feesWithdrawableBy(account);
        if (amount > 0) {
            feesWithdrawn[account] += amount;
            require(collateralToken.transfer(account, amount), "FPMM: transfer failed");
            emit FeesWithdrawn(account, amount);
        }
    }

    function _collectFee(uint256 amount) private {
        if (amount > 0 && totalSupply > 0) {
            accFeesPerShare += (amount * ONE) / totalSupply;
        }
    }

    function entitledFees(address account) private view returns (uint256) {
        return uint256(int256((accFeesPerShare * balanceOf[account]) / ONE) + feeCorrection[account]);
    }

    // Corrections keep each holder's accrued entitlement constant across share movements.
    function _mint(address to, uint256 value) internal override {
        feeCorrection[to] -= int256((accFeesPerShare * value) / ONE);
        super._mint(to, value);
    }

    function _burn(address from, uint256 value) internal override {
        feeCorrection[from] += int256((accFeesPerShare * value) / ONE);
        super._burn(from, value);
    }

    function _transfer(address from, address to, uint256 value) internal override {
        int256 correction = int256((accFeesPerShare * value) / ONE);
        feeCorrection[from] += correction;
        feeCorrection[to] -= correction;
        super._transfer(from, to, value);
    }

    // ------------------------------------------------------------------
    // Views
    // ------------------------------------------------------------------

    function poolBalances() public view returns (uint256 yesBal, uint256 noBal) {
        yesBal = conditionalTokens.balanceOf(yesPositionId, address(this));
        noBal = conditionalTokens.balanceOf(noPositionId, address(this));
    }

    /// @notice Probability-price of an outcome, 1e18-scaled (0.67e18 = 67¢ = 67%).
    function marginalPrice(uint256 outcomeIndex) external view returns (uint256) {
        require(outcomeIndex < 2, "FPMM: bad outcome index");
        (uint256 yesBal, uint256 noBal) = poolBalances();
        if (yesBal + noBal == 0) return 0;
        uint256 otherBal = outcomeIndex == 0 ? noBal : yesBal;
        return (otherBal * ONE) / (yesBal + noBal);
    }

    function onERC1155Received(address, address, uint256, uint256, bytes calldata) external pure returns (bytes4) {
        return IERC1155Receiver.onERC1155Received.selector;
    }

    function onERC1155BatchReceived(address, address, uint256[] calldata, uint256[] calldata, bytes calldata)
        external
        pure
        returns (bytes4)
    {
        return IERC1155Receiver.onERC1155BatchReceived.selector;
    }

    function ceilDiv(uint256 a, uint256 b) private pure returns (uint256) {
        return a == 0 ? 0 : (a - 1) / b + 1;
    }
    function totalFee() public view returns (uint256) {
        return fee + protocolFee;
    }

    /// @notice Anyone may trigger payment; collateral only goes to the fixed treasury.
    function withdrawProtocolFees() external {
        uint256 amount = protocolFeesAccrued;
        protocolFeesAccrued = 0;
        if (amount > 0) {
            require(collateralToken.transfer(feeRecipient, amount), "FPMM: transfer failed");
            emit ProtocolFeesWithdrawn(feeRecipient, amount);
        }
    }

    function _collectTradeFees(uint256 gross, uint256 amount) private {
        uint256 platformAmount = (gross * protocolFee) / ONE;
        // With no LP fee, all rounding dust belongs to the platform.
        if (fee == 0) platformAmount = amount;
        if (platformAmount > 0) {
            protocolFeesAccrued += platformAmount;
            emit ProtocolFeesAccrued(platformAmount);
        }
        _collectFee(amount - platformAmount);
    }
}
