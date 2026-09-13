// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {RegexLib} from "../lib/RegexLib.sol";
import {ConditionalTokens} from "../tokens/ConditionalTokens.sol";
import {IERC20} from "../tokens/ERC20.sol";
import {BodyParser} from "../lib/BodyParser.sol";
import {EmailProof, IDKIMVerifier} from "../dkim/IDKIMVerifier.sol";
import {ILLMJudge} from "../judge/ILLMJudge.sol";
import {JudgePrompt} from "../judge/JudgePrompt.sol";

/// @title HeadlineMarket
/// @notice A binary prediction market on "will the news break?", settled permissionlessly
/// by DKIM proofs of newspaper breaking-news alert emails.
///
/// The market creator configures:
///   - a set of newspaper sources (DKIM domain + regex over the From address),
///   - a condition over the email content: EITHER a regex (subject and/or body; per-source
///     override allowed) OR — judged mode — a natural-language `criteria` (the market's
///     resolution rules) that an on-chain LLM applies to the DKIM-signed Subject line via
///     the `LLMJudge` oracle (see src/judge). Judged mode = empty regex + non-empty criteria.
///   - a K-of-N threshold: how many distinct newspapers must have sent a matching
///     email for the market to resolve YES,
///   - an acceptance window [windowStart, deadline] for the email Date, and a
///     resolution buffer after the deadline during which proofs can still be
///     submitted before anyone may resolve NO.
///
/// The market itself is the oracle for its condition in ConditionalTokens: reaching
/// the threshold reports payouts [1,0] (YES); after deadline + buffer anyone can
/// report [0,1] (NO). Both paths are fully permissionless.
contract HeadlineMarket {
    using RegexLib for string;

    enum ContentField {
        Subject,
        Body,
        SubjectOrBody
    }

    enum Resolution {
        Unresolved,
        Yes,
        No
    }

    struct Source {
        string name; // display name, e.g. "The New York Times"
        string dkimDomain; // DKIM signing domain the proof must carry, e.g. "nytimes.com"
        string fromRegex; // regex the From address must match ("" = any)
        string contentRegex; // per-source override of the market content regex ("" = use default)
    }

    struct Evidence {
        uint32 sourceIndex;
        address submitter;
        uint64 emailTimestamp;
        bytes32 nullifier;
        string subject;
    }

    event ProofAccepted(
        uint256 indexed sourceIndex, address indexed submitter, string subject, uint256 emailTimestamp
    );
    event MarketResolved(Resolution resolution, address indexed resolver);

    // --- static configuration ---
    string public question;
    string public description; // human-readable resolution rules (Polymarket convention)
    string public contentRegex; // default content condition
    ContentField public contentField;
    Source[] internal _sources;
    uint8 public threshold;
    uint64 public windowStart;
    uint64 public deadline;
    uint64 public resolutionBuffer;
    address public creator;
    uint64 public createdAt;

    // Storage (not immutable): markets are EIP-1167 clones of one implementation, so
    // per-market values must live in each clone's own storage.
    ConditionalTokens public conditionalTokens;
    IDKIMVerifier public verifier;
    IERC20 public collateralToken;
    bytes32 public questionId;
    bytes32 public conditionId;
    uint256 public yesPositionId;
    uint256 public noPositionId;
    bool private initialized;

    // --- settlement state ---
    Resolution public resolution;
    uint256 public matchedCount;
    mapping(uint256 => bool) public sourceMatched;
    mapping(bytes32 => bool) public nullifierUsed;
    Evidence[] internal _evidence;

    // --- judged mode (appended after the original layout; clones of older implementations untouched) ---
    /// @notice Natural-language resolution rules judged by `judge` against the signed Subject
    /// ("" = regex mode).
    string public criteria;
    ILLMJudge public judge;

    /// @notice Market configuration bundled in a struct (keeps initialize below the
    /// EVM stack limit and mirrors the factory's CreateMarketParams).
    struct InitConfig {
        string question;
        string description;
        string contentRegex;
        ContentField contentField;
        Source[] sources;
        uint8 threshold;
        uint64 windowStart;
        uint64 deadline;
        uint64 resolutionBuffer;
        string criteria; // judged mode when non-empty (requires contentRegex == "")
    }

    /// @dev Lock the shared implementation so only clones can be initialized.
    constructor() {
        initialized = true;
    }

    function initialize(
        ConditionalTokens _conditionalTokens,
        IDKIMVerifier _verifier,
        IERC20 _collateralToken,
        address _creator,
        ILLMJudge _judge,
        InitConfig calldata cfg
    ) external {
        require(!initialized, "Market: already initialized");
        initialized = true;
        require(cfg.sources.length > 0 && cfg.sources.length <= 32, "Market: 1-32 sources");
        require(cfg.threshold > 0 && cfg.threshold <= cfg.sources.length, "Market: bad threshold");
        require(cfg.deadline > block.timestamp, "Market: deadline in past");
        require(cfg.deadline > cfg.windowStart, "Market: deadline before window start");

        // Validate every regex now so malformed patterns can never brick settlement.
        if (bytes(cfg.contentRegex).length > 0) cfg.contentRegex.validate();
        for (uint256 i = 0; i < cfg.sources.length; i++) {
            require(bytes(cfg.sources[i].dkimDomain).length > 0, "Market: empty domain");
            // Sources must be distinct newspapers: a K-of-N threshold is meaningless if
            // one domain can occupy two slots and settle the market by itself.
            for (uint256 j = 0; j < i; j++) {
                require(
                    keccak256(bytes(cfg.sources[i].dkimDomain)) != keccak256(bytes(cfg.sources[j].dkimDomain)),
                    "Market: duplicate source domain"
                );
            }
            if (bytes(cfg.sources[i].fromRegex).length > 0) cfg.sources[i].fromRegex.validate();
            if (bytes(cfg.sources[i].contentRegex).length > 0) cfg.sources[i].contentRegex.validate();
            _sources.push(cfg.sources[i]);
        }
        bool judged = bytes(cfg.criteria).length > 0;
        if (judged) {
            require(address(_judge) != address(0), "Market: no judge on this factory");
            require(bytes(cfg.contentRegex).length == 0, "Market: regex and criteria are exclusive");
            require(!anySourceHasOverride(cfg.sources), "Market: judged markets take no source overrides");
            require(
                JudgePrompt.isSafeMarketText(bytes(cfg.question), JudgePrompt.MAX_CRITERIA_BYTES)
                    && JudgePrompt.isSafeMarketText(bytes(cfg.criteria), JudgePrompt.MAX_CRITERIA_BYTES),
                "Market: question/criteria must be one line, no '<'"
            );
            criteria = cfg.criteria;
            judge = _judge;
        } else {
            require(
                bytes(cfg.contentRegex).length > 0 || allSourcesHaveOverrides(cfg.sources),
                "Market: no content condition"
            );
        }

        if (cfg.contentField == ContentField.Body) {
            require(BodyParser.substringPattern(cfg.contentRegex), "Market: body anchors unsupported");
            for (uint256 i; i < cfg.sources.length; ++i)
                require(BodyParser.substringPattern(cfg.sources[i].contentRegex), "Market: body anchors unsupported");
        }

        question = cfg.question;
        description = cfg.description;
        contentRegex = cfg.contentRegex;
        contentField = cfg.contentField;
        threshold = cfg.threshold;
        windowStart = cfg.windowStart;
        deadline = cfg.deadline;
        resolutionBuffer = cfg.resolutionBuffer;
        creator = _creator;
        createdAt = uint64(block.timestamp);

        conditionalTokens = _conditionalTokens;
        verifier = _verifier;
        collateralToken = _collateralToken;

        // This market is its own oracle; the market address makes the question unique.
        questionId = keccak256(abi.encodePacked("HEADLINE_MARKET_V1", address(this)));
        _conditionalTokens.prepareCondition(address(this), questionId, 2);
        conditionId = _conditionalTokens.getConditionId(address(this), questionId, 2);
        yesPositionId =
            _conditionalTokens.getPositionId(_collateralToken, _conditionalTokens.getCollectionId(conditionId, 1));
        noPositionId =
            _conditionalTokens.getPositionId(_collateralToken, _conditionalTokens.getCollectionId(conditionId, 2));
    }

    // ------------------------------------------------------------------
    // Settlement — fully permissionless
    // ------------------------------------------------------------------

    /// @notice Submit a DKIM proof of a newspaper alert email. Anyone may call.
    /// Accepting the `threshold`-th distinct source resolves the market YES.
    function submitProof(uint256 sourceIndex, EmailProof calldata proof) external {
        require(resolution == Resolution.Unresolved, "Market: already resolved");
        require(sourceIndex < _sources.length, "Market: bad source index");
        require(!sourceMatched[sourceIndex], "Market: source already matched");
        require(!nullifierUsed[proof.emailNullifier], "Market: email already used");
        require(verifier.verify(proof), "Market: invalid DKIM proof");

        Source storage src = _sources[sourceIndex];
        require(
            keccak256(bytes(proof.domainName)) == keccak256(bytes(src.dkimDomain)), "Market: wrong DKIM domain"
        );
        require(proof.timestamp >= windowStart, "Market: email before window");
        require(proof.timestamp <= deadline, "Market: email after deadline");
        if (bytes(src.fromRegex).length > 0) {
            require(src.fromRegex.matches(proof.fromAddress), "Market: from address mismatch");
        }
        require(contentMatches(src, proof), "Market: content regex mismatch");

        nullifierUsed[proof.emailNullifier] = true;
        sourceMatched[sourceIndex] = true;
        matchedCount++;
        _evidence.push(
            Evidence({
                sourceIndex: uint32(sourceIndex),
                submitter: msg.sender,
                emailTimestamp: uint64(proof.timestamp),
                nullifier: proof.emailNullifier,
                subject: proof.subject
            })
        );
        emit ProofAccepted(sourceIndex, msg.sender, proof.subject, proof.timestamp);

        if (matchedCount >= threshold) {
            resolution = Resolution.Yes;
            uint256[] memory payouts = new uint256[](2);
            payouts[0] = 1; // YES
            conditionalTokens.reportPayouts(questionId, payouts);
            emit MarketResolved(Resolution.Yes, msg.sender);
        }
    }

    /// @notice After the deadline plus the resolution buffer, anyone can resolve NO.
    function resolveNo() external {
        require(resolution == Resolution.Unresolved, "Market: already resolved");
        require(block.timestamp > uint256(deadline) + resolutionBuffer, "Market: too early to resolve NO");
        resolution = Resolution.No;
        uint256[] memory payouts = new uint256[](2);
        payouts[1] = 1; // NO
        conditionalTokens.reportPayouts(questionId, payouts);
        emit MarketResolved(Resolution.No, msg.sender);
    }

    /// @notice Dry-run a proof against a source's conditions without spending state.
    /// Lets frontends and settlement bots check acceptance before sending a tx.
    function checkProof(uint256 sourceIndex, EmailProof calldata proof)
        external
        view
        returns (bool ok, string memory reason)
    {
        if (resolution != Resolution.Unresolved) return (false, "already resolved");
        if (sourceIndex >= _sources.length) return (false, "bad source index");
        if (sourceMatched[sourceIndex]) return (false, "source already matched");
        if (nullifierUsed[proof.emailNullifier]) return (false, "email already used");
        if (!verifier.verify(proof)) return (false, "invalid DKIM proof");
        Source storage src = _sources[sourceIndex];
        if (keccak256(bytes(proof.domainName)) != keccak256(bytes(src.dkimDomain))) {
            return (false, "wrong DKIM domain");
        }
        if (proof.timestamp < windowStart) return (false, "email before window");
        if (proof.timestamp > deadline) return (false, "email after deadline");
        if (bytes(src.fromRegex).length > 0 && !src.fromRegex.matches(proof.fromAddress)) {
            return (false, "from address mismatch");
        }
        if (!contentMatches(src, proof)) {
            if (bytes(criteria).length > 0) {
                ILLMJudge.Verdict v = judgedVerdict(proof);
                if (v == ILLMJudge.Verdict.No) return (false, "judge verdict: NO");
                return (false, "no judge verdict for this email yet");
            }
            return (false, "content regex mismatch");
        }
        return (true, "");
    }

    // ------------------------------------------------------------------
    // Views
    // ------------------------------------------------------------------

    function getSources() external view returns (Source[] memory) {
        return _sources;
    }

    function getEvidence() external view returns (Evidence[] memory) {
        return _evidence;
    }

    function sourceCount() external view returns (uint256) {
        return _sources.length;
    }

    // ------------------------------------------------------------------
    // Internals
    // ------------------------------------------------------------------

    function contentMatches(Source storage src, EmailProof calldata proof) internal view returns (bool) {
        if (bytes(criteria).length > 0) {
            return judgedVerdict(proof) == ILLMJudge.Verdict.Yes;
        }
        string memory pattern = bytes(src.contentRegex).length > 0 ? src.contentRegex : contentRegex;
        if (bytes(pattern).length == 0) return true; // no content condition configured
        if (contentField == ContentField.Subject) return pattern.matches(proof.subject);
        if (contentField == ContentField.Body) return bodyMatches(pattern, proof);
        return pattern.matches(proof.subject) || bodyMatches(pattern, proof);
    }

    function bodyMatches(string memory pattern, EmailProof calldata proof) internal pure returns (bool) {
        return proof.canonicalBody.length > 0 && BodyParser.substringPattern(pattern) && pattern.matches(proof.bodyExcerpt);
    }

    /// @notice The judge's verdict for this email under this market's rules — computed from the
    /// Subject line parsed out of the RSA-signed header (never from `proof.subject`), so the
    /// verdict key is bound to the signed bytes. None = not judged yet / subject unreadable.
    function judgedVerdict(EmailProof calldata proof) public view returns (ILLMJudge.Verdict) {
        (bytes memory subject, bool ok) = JudgePrompt.subjectFromHeader(proof.header);
        if (!ok || !JudgePrompt.isSafeSubject(subject)) return ILLMJudge.Verdict.None;
        return judge.verdictOf(JudgePrompt.promptKey(question, criteria, subject));
    }

    /// @notice Prompt key the judge must answer for this email (for bots/UI to request a verdict).
    function promptKeyFor(EmailProof calldata proof) external view returns (bytes32 key, bytes memory subject, bool ok) {
        (subject, ok) = JudgePrompt.subjectFromHeader(proof.header);
        if (!ok || !JudgePrompt.isSafeSubject(subject)) return (bytes32(0), subject, false);
        return (JudgePrompt.promptKey(question, criteria, subject), subject, true);
    }

    function anySourceHasOverride(Source[] memory sources_) private pure returns (bool) {
        for (uint256 i = 0; i < sources_.length; i++) {
            if (bytes(sources_[i].contentRegex).length > 0) return true;
        }
        return false;
    }

    function allSourcesHaveOverrides(Source[] memory sources_) private pure returns (bool) {
        for (uint256 i = 0; i < sources_.length; i++) {
            if (bytes(sources_[i].contentRegex).length == 0) return false;
        }
        return true;
    }
}
