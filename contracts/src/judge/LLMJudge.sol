// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {GasKillerSDK} from "gas-killer-sdk/GasKillerSDK.sol";
import {ILLMJudge} from "./ILLMJudge.sol";
import {JudgePrompt} from "./JudgePrompt.sol";
import {TokenTable} from "./TokenTable.sol";

/// @title LLMJudge
/// @notice A Gas Killer consumer that turns sharded on-chain LLM inference (Qwen3.5-35B-A3B,
/// engine v3) into settlement verdicts for judged markets.
///
/// Shape: `fulfil` / `fulfilResumed` / `settlePrefix` have EXACTLY the signatures (selectors)
/// of `GasKillerChat35Sharded`, so an unmodified Gas Killer fleet (service PR #321 validator
/// gate, `GK_SHARD_CONSUMER = this`) serves it: the router's shard coordinator runs the prompt
/// ids through k-of-N operator committees, assembles the commit chain `pipelineRoot`, and
/// every operator verifies that chain (and the segments it executed itself) before
/// BLS-signing this tracked call.
///
/// What differs from the chat consumer is what the tracked call CHECKS. It runs inside the
/// operators' simulation environment, where the model's tokenizer table is mounted as overlay
/// code, and:
///   1. strips the pinned chat-template scaffold ids (prefix/suffix) and requires every user
///      id to be a base-vocab token (no control tokens);
///   2. detokenizes the user ids back to bytes — the prompt TEXT — and splits it into the
///      per-market prefix and the per-email tail (JudgePrompt.splitUserText);
///   3. re-tokenizes both pieces with the canonical greedy tokenizer and requires equality —
///      so a submitter cannot choose among byte-equal segmentations;
///   4. maps the single generated token to YES / NO and records
///      `verdicts[keccak256(text)]` — ONE storage write plus one log.
/// Anything else (wrong scaffold, non-canonical ids, unparseable answer, already judged)
/// emits `JudgeRejected` and writes nothing: a tracked call must never revert, because the
/// analyzer still signs a counter-only payload for a reverted simulation.
///
/// Prefix resume: a market's prefix (rules) is warmed once through `settlePrefix`, after which
/// `fulfilResumed` only pays for the subject. The contract binds the resumed prompt's prefix
/// ids to the settled prefix by hash; the operator gate binds the execution lineage.
///
/// Binding to the email is the MARKET's job and happens on the real chain: `HeadlineMarket`
/// rebuilds the same text from its own question/criteria and the Subject parsed out of the
/// DKIM-signed header (JudgePrompt), and consumes `verdictOf(keccak256(text))`. So a verdict
/// can only ever move a market for a genuine, in-window email of a configured newspaper.
///
/// Trust: the verdict is attested by the Gas Killer operator quorum (≥66% stake), not proven
/// on-chain — until the re-execution slasher ships. Deterministic integer inference, pinned
/// weights (`weightsManifest`) and pinned template ids make every verdict re-executable.
contract LLMJudge is GasKillerSDK, ILLMJudge {
    // ------------------------------------------------------------------ model pins
    /// @notice Overlay manifest of the model (keccak(weights) ++ keccak(tokenizer)); the only
    /// on-chain commitment to the weights.
    bytes32 public immutable weightsManifest;
    /// @notice Number of weight chunks (tokenizer chunks follow them in overlay index space).
    uint256 public immutable weightChunks;
    uint256 public immutable tokenizerChunks;
    uint256 public immutable tokenizerLength;
    /// @notice First special/added token id: canonical user ids must be below it.
    uint32 public immutable specialBase;
    uint256 public constant MAX_NEW_TOKENS = 1;

    uint32[] private _prefixIds; // chat-template scaffold before the user text
    uint32[] private _suffixIds; // … and after it (incl. the empty <think> block)
    uint32[] private _yesIds;
    uint32[] private _noIds;

    // ------------------------------------------------------------------ settlement state
    /// @dev promptKey => Verdict. Written only by fulfil/fulfilResumed (one STORE each).
    mapping(bytes32 => uint8) private _verdicts;
    /// @dev prefixRoot => keccak256(abi.encodePacked(prefixIds)). Written only by settlePrefix.
    mapping(bytes32 => bytes32) public prefixKeyOf;

    // ------------------------------------------------------------------ admin
    address public owner;

    event JudgeVerdict(
        uint256 indexed transitionIndex,
        bytes32 indexed promptKey,
        bytes32 indexed pipelineRoot,
        uint8 verdict,
        uint32 answerId,
        bytes userText
    );
    event JudgeRejected(uint256 indexed transitionIndex, bytes32 indexed pipelineRoot, string reason);
    /// @notice Same shape as GasKillerChat35Sharded.PrefixSettled.
    event PrefixSettled(uint256 indexed transitionIndex, bytes32 indexed prefixRoot, uint32[] prefixIds);
    event GasKillerConfigUpdated(address avs, address blsSignatureChecker, uint256 blockStaleMeasure);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    error NotOwner();
    error OverlayNotMounted();

    struct ModelConfig {
        bytes32 weightsManifest;
        uint256 weightChunks;
        uint256 tokenizerChunks;
        uint256 tokenizerLength;
        uint32 specialBase;
        uint32[] prefixIds;
        uint32[] suffixIds;
        uint32[] yesIds;
        uint32[] noIds;
    }

    constructor(address _owner, address _avs, address _blsSigChecker, ModelConfig memory m) {
        owner = _owner;
        _setAvsAddress(_avs);
        _setBlsSignatureChecker(_blsSigChecker);
        weightsManifest = m.weightsManifest;
        weightChunks = m.weightChunks;
        tokenizerChunks = m.tokenizerChunks;
        tokenizerLength = m.tokenizerLength;
        specialBase = m.specialBase;
        _prefixIds = m.prefixIds;
        _suffixIds = m.suffixIds;
        _yesIds = m.yesIds;
        _noIds = m.noIds;
        require(m.prefixIds.length > 0 && m.suffixIds.length > 0, "Judge: scaffold");
        require(m.yesIds.length > 0 && m.noIds.length > 0, "Judge: answer ids");
    }

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    /// @notice Follow an operator-set redeploy (the AVS/checker addresses are deployment
    /// properties, not protocol constants). Whoever holds `owner` can point this contract at a
    /// checker they control — keep it behind a multisig/timelock.
    function setGasKillerConfig(address _avs, address _blsSigChecker, uint256 _blockStaleMeasure) external onlyOwner {
        _setAvsAddress(_avs);
        _setBlsSignatureChecker(_blsSigChecker);
        _setBlockStaleMeasure(_blockStaleMeasure);
        emit GasKillerConfigUpdated(_avs, _blsSigChecker, _blockStaleMeasure);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    // ------------------------------------------------------------------ tracked calls

    /// @notice Fresh sharded-inference settlement (selector-identical to GasKillerChat35Sharded.fulfil).
    /// @dev Only meaningful inside the Gas Killer simulation (overlay mounted). A direct
    ///      on-chain call reverts `OverlayNotMounted` — which also means it can never bump the
    ///      transition counter and invalidate an in-flight signed payload.
    function fulfil(
        uint32[] calldata promptIds,
        uint256 maxNewTokens,
        uint32[] calldata answerIds,
        bytes32 pipelineRoot
    ) external trackState {
        _requireOverlay();
        _judge(promptIds, maxNewTokens, answerIds, pipelineRoot, bytes32(0));
    }

    /// @notice Settlement of a run that RESUMED from a warmed prefix (selector-identical to
    /// GasKillerChat35Sharded.fulfilResumed). The prompt's prefix ids must hash to the ids
    /// admitted for `prefixRoot` by `settlePrefix`.
    function fulfilResumed(
        uint32[] calldata promptIds,
        uint256 maxNewTokens,
        uint32[] calldata answerIds,
        bytes32 pipelineRoot,
        bytes32 prefixRoot
    ) external trackState {
        _requireOverlay();
        bytes32 pk = prefixKeyOf[prefixRoot];
        if (pk == bytes32(0)) {
            _reject(stateTransitionCount(), pipelineRoot, "prefix not settled");
            return;
        }
        _judge(promptIds, maxNewTokens, answerIds, pipelineRoot, pk);
    }

    /// @notice Admit a committee-verified, prefill-only prefix run as a resume anchor
    /// (selector-identical to GasKillerChat35Sharded.settlePrefix). The prefix ids must be the
    /// scaffold prefix followed by the canonical tokenization of a well-formed market prefix
    /// text (ending in the template's subject lead-in).
    function settlePrefix(uint32[] calldata prefixIds, bytes32 prefixRoot) external trackState {
        _requireOverlay();
        uint256 t = stateTransitionCount();
        if (prefixRoot == bytes32(0)) return _reject(t, prefixRoot, "zero prefix root");
        if (prefixKeyOf[prefixRoot] != bytes32(0)) return _reject(t, prefixRoot, "prefix already settled");
        uint256 np = _prefixIds.length;
        if (prefixIds.length <= np) return _reject(t, prefixRoot, "bad chat scaffold");
        for (uint256 i = 0; i < np; ++i) {
            if (prefixIds[i] != _prefixIds[i]) return _reject(t, prefixRoot, "bad chat scaffold");
        }
        uint32[] memory user = new uint32[](prefixIds.length - np);
        for (uint256 i = 0; i < user.length; ++i) {
            if (prefixIds[np + i] >= specialBase) return _reject(t, prefixRoot, "bad chat scaffold");
            user[i] = prefixIds[np + i];
        }
        bytes memory table = _table();
        bytes memory text = TokenTable.detokenize(table, user);
        (uint256 split, bool found) = JudgePrompt.splitUserText(text);
        if (!found || split != text.length) return _reject(t, prefixRoot, "not a prompt prefix");
        if (!_sameIds(TokenTable.greedyTokenize(table, text, specialBase), user)) {
            return _reject(t, prefixRoot, "non-canonical tokenization");
        }
        prefixKeyOf[prefixRoot] = keccak256(abi.encodePacked(prefixIds)); // the single STORE
        emit PrefixSettled(t, prefixRoot, prefixIds);
    }

    // ------------------------------------------------------------------ views

    function verdictOf(bytes32 key) external view returns (Verdict) {
        return Verdict(_verdicts[key]);
    }

    function promptKey(string calldata question, string calldata criteria, bytes calldata subject)
        external
        pure
        returns (bytes32)
    {
        return JudgePrompt.promptKey(question, criteria, subject);
    }

    function userText(string calldata question, string calldata criteria, bytes calldata subject)
        external
        pure
        returns (bytes memory)
    {
        return JudgePrompt.userText(question, criteria, subject);
    }

    /// @notice Canonical prompt ids for a (question, criteria, subject) — scaffold included,
    /// piecewise (prefix ids ++ tail ids). Only answers in an environment with the overlay
    /// mounted (operator env, anvil + setCode); the bot mirrors this in JS from the same
    /// tokenizer blob.
    /// @return ids The full prompt ids
    /// @return prefixLen How many leading ids form the resumable prefix (scaffold prefix + market prefix)
    function canonicalPromptIds(string calldata question, string calldata criteria, bytes calldata subject)
        external
        view
        returns (uint32[] memory ids, uint256 prefixLen)
    {
        bytes memory table = _table();
        uint32[] memory pre = TokenTable.greedyTokenize(table, JudgePrompt.prefixText(question, criteria), specialBase);
        uint32[] memory tail = TokenTable.greedyTokenize(table, JudgePrompt.tailText(subject), specialBase);
        ids = new uint32[](_prefixIds.length + pre.length + tail.length + _suffixIds.length);
        uint256 k = 0;
        for (uint256 i = 0; i < _prefixIds.length; ++i) {
            ids[k++] = _prefixIds[i];
        }
        for (uint256 i = 0; i < pre.length; ++i) {
            ids[k++] = pre[i];
        }
        prefixLen = k;
        for (uint256 i = 0; i < tail.length; ++i) {
            ids[k++] = tail[i];
        }
        for (uint256 i = 0; i < _suffixIds.length; ++i) {
            ids[k++] = _suffixIds[i];
        }
    }

    function scaffold() external view returns (uint32[] memory prefix, uint32[] memory suffix) {
        return (_prefixIds, _suffixIds);
    }

    function answerIdSets() external view returns (uint32[] memory yes, uint32[] memory no) {
        return (_yesIds, _noIds);
    }

    /// @notice Map a generated token id to a verdict (0 = neither).
    function classify(uint32 id) external view returns (uint8) {
        return _classify(id);
    }

    // ------------------------------------------------------------------ internals

    /// @dev Shared body of fulfil/fulfilResumed. `requiredPrefixKey` non-zero ⇒ the prompt's
    ///      prefix ids (scaffold prefix ++ canonical prefix-text ids) must hash to it.
    function _judge(
        uint32[] calldata promptIds,
        uint256 maxNewTokens,
        uint32[] calldata answerIds,
        bytes32 pipelineRoot,
        bytes32 requiredPrefixKey
    ) private {
        uint256 t = stateTransitionCount();
        if (pipelineRoot == bytes32(0)) return _reject(t, pipelineRoot, "zero pipeline root");
        if (maxNewTokens != MAX_NEW_TOKENS) return _reject(t, pipelineRoot, "maxNewTokens must be 1");
        if (answerIds.length == 0) return _reject(t, pipelineRoot, "empty answer");

        (uint32[] memory userIds, bool scaffoldOk) = _stripScaffold(promptIds);
        if (!scaffoldOk) return _reject(t, pipelineRoot, "bad chat scaffold");

        bytes memory table = _table();
        bytes memory text = TokenTable.detokenize(table, userIds);
        (uint256 split, bool found) = JudgePrompt.splitUserText(text);
        if (!found || split == text.length) return _reject(t, pipelineRoot, "malformed prompt");

        // canonical = greedy(prefixText) ++ greedy(tailText)
        uint32[] memory pre = TokenTable.greedyTokenize(table, _slice(text, 0, split), specialBase);
        if (!_isPrefixOf(pre, userIds)) return _reject(t, pipelineRoot, "non-canonical tokenization");
        uint32[] memory tail = TokenTable.greedyTokenize(table, _slice(text, split, text.length), specialBase);
        if (pre.length + tail.length != userIds.length || !_matchesAt(tail, userIds, pre.length)) {
            return _reject(t, pipelineRoot, "non-canonical tokenization");
        }
        if (requiredPrefixKey != bytes32(0)) {
            uint256 plen = _prefixIds.length + pre.length;
            if (keccak256(abi.encodePacked(promptIds[:plen])) != requiredPrefixKey) {
                return _reject(t, pipelineRoot, "prefix mismatch");
            }
        }

        bytes32 key = keccak256(text);
        if (_verdicts[key] != 0) return _reject(t, pipelineRoot, "already judged");

        uint8 v = _classify(answerIds[0]);
        if (v == 0) return _reject(t, pipelineRoot, "answer is not YES/NO");

        _verdicts[key] = v; // the single consumer STORE
        emit JudgeVerdict(t, key, pipelineRoot, v, answerIds[0], text);
    }

    function _requireOverlay() private view {
        if (TokenTable.overlayChunkAddress(weightsManifest, weightChunks).code.length == 0) {
            revert OverlayNotMounted();
        }
    }

    function _table() private view returns (bytes memory) {
        return TokenTable.readOverlay(weightsManifest, weightChunks, tokenizerChunks, tokenizerLength);
    }

    function _reject(uint256 t, bytes32 pipelineRoot, string memory reason) private {
        emit JudgeRejected(t, pipelineRoot, reason);
    }

    function _classify(uint32 id) private view returns (uint8) {
        for (uint256 i = 0; i < _yesIds.length; ++i) {
            if (_yesIds[i] == id) return uint8(Verdict.Yes);
        }
        for (uint256 i = 0; i < _noIds.length; ++i) {
            if (_noIds[i] == id) return uint8(Verdict.No);
        }
        return 0;
    }

    /// @dev Require prefix/suffix scaffold ids verbatim and every user id < specialBase.
    function _stripScaffold(uint32[] calldata ids) private view returns (uint32[] memory user, bool ok) {
        uint256 np = _prefixIds.length;
        uint256 ns = _suffixIds.length;
        if (ids.length <= np + ns) return (user, false);
        for (uint256 i = 0; i < np; ++i) {
            if (ids[i] != _prefixIds[i]) return (user, false);
        }
        for (uint256 i = 0; i < ns; ++i) {
            if (ids[ids.length - ns + i] != _suffixIds[i]) return (user, false);
        }
        uint256 n = ids.length - np - ns;
        user = new uint32[](n);
        for (uint256 i = 0; i < n; ++i) {
            uint32 id = ids[np + i];
            if (id >= specialBase) return (user, false);
            user[i] = id;
        }
        return (user, true);
    }

    function _isPrefixOf(uint32[] memory a, uint32[] memory b) private pure returns (bool) {
        if (a.length > b.length) return false;
        for (uint256 i = 0; i < a.length; ++i) {
            if (a[i] != b[i]) return false;
        }
        return true;
    }

    function _matchesAt(uint32[] memory a, uint32[] memory b, uint256 at) private pure returns (bool) {
        if (at + a.length > b.length) return false;
        for (uint256 i = 0; i < a.length; ++i) {
            if (a[i] != b[at + i]) return false;
        }
        return true;
    }

    function _sameIds(uint32[] memory a, uint32[] memory b) private pure returns (bool) {
        return a.length == b.length && _isPrefixOf(a, b);
    }

    function _slice(bytes memory s, uint256 a, uint256 b) private pure returns (bytes memory out) {
        out = new bytes(b - a);
        assembly ("memory-safe") {
            mcopy(add(out, 0x20), add(add(s, 0x20), a), sub(b, a))
        }
    }
}
