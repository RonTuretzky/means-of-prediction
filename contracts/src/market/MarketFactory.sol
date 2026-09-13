// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ConditionalTokens} from "../tokens/ConditionalTokens.sol";
import {IERC20} from "../tokens/ERC20.sol";
import {IDKIMVerifier} from "../dkim/IDKIMVerifier.sol";
import {ILLMJudge} from "../judge/ILLMJudge.sol";
import {HeadlineMarket} from "./HeadlineMarket.sol";
import {FPMM} from "./FPMM.sol";
import {Clones} from "../utils/Clones.sol";

/// @title MarketFactory
/// @notice Permissionless factory: anyone can open a headline market. Deploys the
/// market (which registers itself as oracle of a fresh CTF condition) plus its FPMM
/// trading pool, and optionally seeds initial liquidity from the creator in the same
/// transaction. Collateral token and trading fee are configurable per market.
contract MarketFactory {
    struct CreateMarketParams {
        // market question
        string question;
        string description; // human-readable resolution rules
        // settlement conditions (regex mode: contentRegex; judged mode: criteria + empty regex)
        string contentRegex;
        string criteria;
        HeadlineMarket.ContentField contentField;
        HeadlineMarket.Source[] sources;
        uint8 threshold; // K of N sources required for YES
        uint64 windowStart; // earliest accepted email Date (0 = any)
        uint64 deadline; // latest accepted email Date
        uint64 resolutionBuffer; // grace period after deadline before NO is resolvable
        // market token management
        IERC20 collateralToken;
        uint256 fee; // FPMM trading fee, 1e18-scale
        uint256 initialLiquidity; // pulled from creator if > 0
        uint256[] distributionHint; // optional initial odds, e.g. [3, 1]
    }

    struct MarketRecord {
        address market;
        address fpmm;
    }

    event MarketCreated(
        uint256 indexed marketId,
        address indexed market,
        address indexed fpmm,
        address creator,
        string question,
        address collateralToken,
        uint64 deadline
    );

    ConditionalTokens public immutable conditionalTokens;
    IDKIMVerifier public immutable verifier;
    /// EIP-1167 implementations: every market/FPMM is a 45-byte clone of these.
    address public immutable marketImplementation;
    address public immutable fpmmImplementation;
    /// @notice LLM verdict oracle for judged markets (address(0) = judged mode unavailable).
    ILLMJudge public immutable judge;
    uint256 public immutable protocolFee;
    address public immutable feeRecipient;

    MarketRecord[] internal _markets;

    constructor(
        ConditionalTokens _conditionalTokens,
        IDKIMVerifier _verifier,
        address _marketImplementation,
        address _fpmmImplementation,
        ILLMJudge _judge,
        uint256 _protocolFee,
        address _feeRecipient
    ) {
        require(_protocolFee <= 5e16, "Factory: protocol fee above 5%");
        require(_protocolFee == 0 || _feeRecipient != address(0), "Factory: missing fee recipient");
        conditionalTokens = _conditionalTokens;
        verifier = _verifier;
        marketImplementation = _marketImplementation;
        fpmmImplementation = _fpmmImplementation;
        judge = _judge;
        protocolFee = _protocolFee;
        feeRecipient = _feeRecipient;
    }

    function createMarket(CreateMarketParams calldata params)
        external
        returns (HeadlineMarket market, FPMM fpmm)
    {
        market = HeadlineMarket(Clones.clone(marketImplementation));
        market.initialize(conditionalTokens, verifier, params.collateralToken, msg.sender, judge, _initConfig(params));
        fpmm = FPMM(Clones.clone(fpmmImplementation));
        fpmm.initialize(conditionalTokens, params.collateralToken, market.conditionId(), params.fee, protocolFee, feeRecipient);

        if (params.initialLiquidity > 0) {
            require(
                params.collateralToken.transferFrom(msg.sender, address(this), params.initialLiquidity),
                "Factory: transfer failed"
            );
            params.collateralToken.approve(address(fpmm), params.initialLiquidity);
            fpmm.addFunding(params.initialLiquidity, params.distributionHint, msg.sender);
        }

        uint256 marketId = _markets.length;
        _markets.push(MarketRecord({market: address(market), fpmm: address(fpmm)}));
        emit MarketCreated(
            marketId,
            address(market),
            address(fpmm),
            msg.sender,
            params.question,
            address(params.collateralToken),
            params.deadline
        );
    }

    /// @dev Built in a helper to keep `createMarket` under the EVM stack limit.
    function _initConfig(CreateMarketParams calldata params)
        private
        pure
        returns (HeadlineMarket.InitConfig memory cfg)
    {
        cfg.question = params.question;
        cfg.description = params.description;
        cfg.contentRegex = params.contentRegex;
        cfg.contentField = params.contentField;
        cfg.sources = params.sources;
        cfg.threshold = params.threshold;
        cfg.windowStart = params.windowStart;
        cfg.deadline = params.deadline;
        cfg.resolutionBuffer = params.resolutionBuffer;
        cfg.criteria = params.criteria;
    }

    function marketCount() external view returns (uint256) {
        return _markets.length;
    }

    function getMarket(uint256 marketId) external view returns (MarketRecord memory) {
        return _markets[marketId];
    }

    function getAllMarkets() external view returns (MarketRecord[] memory) {
        return _markets;
    }
}
