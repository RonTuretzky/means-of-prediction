// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity ^0.8.27;

import {ERC165} from "../oz/utils/introspection/ERC165.sol";
import {IERC165} from "../oz/utils/introspection/IERC165.sol";
import {IGasKillerSDK} from "./interface/IGasKillerSDK.sol";
import {IGasKillerSDKBatch, TaskSubmission} from "./interface/IGasKillerSDKBatch.sol";
import {IGasKillerValueBound} from "./interface/IGasKillerValueBound.sol";
import {StateTracker} from "./StateTracker.sol";
import {TransitionGuard} from "./TransitionGuard.sol";
import {StateChangeHandlerLib, StateUpdateType} from "./StateChangeHandlerLib.sol";
import {ISchnorrStakeRegistry} from "./interface/ISchnorrStakeRegistry.sol";

/// @title GasKillerSDK
/// @notice Base contract for Gas Killer targets. Authorises a state transition with a
///         **single** aggregate Schnorr signature verified against a `SchnorrStakeRegistry`
///         (constant gas, non-signer subtraction) and applies the signed state updates.
///
/// @dev The signed message is `sha256(abi.encode(transitionIndex, address(this),
///      targetFunction, storageUpdates))` for a transition settled with no ETH, and
///      `sha256(abi.encode(transitionIndex, address(this), targetFunction, storageUpdates,
///      value))` for one settled with `value` wei. It is independent of the signature scheme,
///      so the off-chain digest and the slashing/fraud-proof machinery do not depend on it.
///
///      Binding the value is what makes inbound ETH safe: a tracked function that credits
///      `msg.value` replays as plain `STORE` updates, so without it anyone could settle a
///      deposit while sending nothing. A zero-value transition keeps the original four-field
///      encoding, so every zero-value signature is unchanged; the two encodings cannot collide
///      because their heads differ in length.
///
///      Both entrypoints are `guardTransition`-protected (see `TransitionGuard`): a `CALL`
///      state update runs arbitrary external code mid-transition, so re-entering
///      `verifyAndUpdate` with the *next* transition's valid signature would otherwise
///      interleave two signed transitions. The same transient flag is queryable as
///      `inTransition()` so external readers can reject mid-transition state.
///
///      Both entrypoints are also `payable`. The value is part of what the quorum signs, so a
///      transition settles only with the value it was analyzed with; see the per-function docs.
///
///      Nested settlement is opt-in through `GasKillerNestedSDK`, so a consumer that never
///      nests does not carry its bytecode; a `NESTED` op settled here reverts.
abstract contract GasKillerSDK is
    StateTracker,
    TransitionGuard,
    ERC165,
    IGasKillerSDK,
    IGasKillerSDKBatch,
    IGasKillerValueBound
{
    struct GasKillerSDKStorage {
        address avsAddress;
        ISchnorrStakeRegistry registry;
        uint96 blockStaleMeasure;
    }

    // keccak256(abi.encode(uint256(keccak256("gaskiller.SchnorrGasKillerSDK.storage")) - 1)) & ~bytes32(uint256(0xff))
    bytes32 private constant STORAGE_LOCATION = 0x1d6f9f139320a34a32f3b29eb8638270178e831962a74100c9e8b433f21e1200;

    uint256 private constant DEFAULT_BLOCK_STALE_MEASURE = 300;

    error FutureBlockNumber();
    error StaleBlockNumber();
    error InvalidTransitionIndex();
    error InvalidSignature();
    error InvalidQuorumSignature();
    error EmptyBatch();
    error InsufficientBatchValue(uint256 sent, uint256 required);
    error BlockStaleMeasureOverflow();

    /// @notice Verify an aggregate Schnorr quorum signature and apply the state updates.
    /// @dev `msg.value` is bound into the digest, so the transition settles only with exactly
    ///      the value the task was analyzed with: a deposit cannot be credited without its ETH,
    ///      and no surplus can be sent. Value moved by `CALL`/`CREATE`/`CREATE2` updates is fixed
    ///      inside the signed `storageUpdates` and paid out of this contract's balance, which
    ///      includes `msg.value`; a shortfall reverts the whole transition (`RevertingContext` for
    ///      a CALL, `DeploymentFailed` for a CREATE/CREATE2).
    /// @param msgHash             the task digest (recomputed and checked below).
    /// @param referenceBlockNumber block at which stake/keys are evaluated by the registry.
    /// @param storageUpdates      ABI-encoded `(StateUpdateType[], bytes[])`.
    /// @param transitionIndex     expected `stateTransitionCount() - 1`.
    /// @param targetFunction      selector bound into the digest.
    /// @param s                   aggregate Schnorr response scalar.
    /// @param Raddr               aggregate nonce address `address(R)`.
    /// @param nonSigners          operators that did not sign, strictly ascending.
    function verifyAndUpdate(
        bytes32 msgHash,
        uint32 referenceBlockNumber,
        bytes calldata storageUpdates,
        uint256 transitionIndex,
        bytes4 targetFunction,
        uint256 s,
        address Raddr,
        address[] calldata nonSigners
    ) external payable guardTransition {
        _verifyAndUpdateOne(
            msgHash,
            referenceBlockNumber,
            storageUpdates,
            transitionIndex,
            targetFunction,
            msg.value,
            s,
            Raddr,
            nonSigners
        );
    }

    /// @notice Verify and apply a sequence of independently signed state transitions in
    ///         one transaction, amortizing the intrinsic and cold-access costs across the
    ///         batch (sub-transitions after the first verify at warm-access prices).
    /// @dev Each applied submission is checked exactly as a standalone `verifyAndUpdate`
    ///      would check it — same digest, same registry verification — so batching changes
    ///      nothing for the off-chain signing path. Transitions apply in order; the
    ///      `guardTransition` latch is held across the whole batch, and any failing
    ///      sub-transition reverts the entire batch.
    ///
    ///      A submission whose `transitionIndex` is already settled is SKIPPED (not
    ///      validated, not applied) rather than reverting the batch: settlement is
    ///      permissionless, so a third party who lifts one submission from the mempool
    ///      and settles it standalone could otherwise nullify the whole batch with one
    ///      cheap front-run. An index can only ever be consumed by a quorum-signed
    ///      transition for this contract, so a skipped item's transition has already
    ///      happened. Reverts (`InvalidTransitionIndex`) only on a genuine gap — an index
    ///      above the next expected one.
    ///
    ///      Batch assemblers: a `CALL` state update forwards all remaining gas to its target
    ///      with no cap (see `StateChangeHandlerLib`). A greedy/griefing target in an early
    ///      sub-transition can therefore starve every later one in the same batch, reverting
    ///      the whole (atomic) batch — no partial-state hazard, but it does nullify the
    ///      amortization this function exists for.
    ///
    ///      Each submission's digest binds its own `value`, and `msg.value` must cover the sum
    ///      over the submissions actually applied (`InsufficientBatchValue` otherwise), so no
    ///      applied transition is credited ETH the batch did not bring. The check is "covers"
    ///      rather than "equals" because a skipped submission must not revert the batch. The
    ///      surplus, such as a front-run item's share, is refunded to `msg.sender` once every
    ///      update has applied. A sender that can't accept it leaves it in this contract
    ///      rather than reverting the batch.
    /// @param submissions The transitions to apply, in order of ascending transition index.
    function verifyAndUpdateBatch(TaskSubmission[] calldata submissions) external payable guardTransition {
        uint256 len = submissions.length;
        require(len != 0, EmptyBatch());
        uint256 required;
        for (uint256 i = 0; i < len; ++i) {
            TaskSubmission calldata sub = submissions[i];
            // Already settled (e.g. front-run or redelivered) → skip, don't poison the batch.
            if (sub.transitionIndex + 1 <= stateTransitionCount()) continue;
            required += sub.value;
            _verifyAndUpdateOne(
                sub.msgHash,
                sub.referenceBlockNumber,
                sub.storageUpdates,
                sub.transitionIndex,
                sub.targetFunction,
                sub.value,
                sub.s,
                sub.Raddr,
                sub.nonSigners
            );
        }
        require(msg.value >= required, InsufficientBatchValue(msg.value, required));
        if (msg.value > required) {
            // Under the latch, so the refund can't re-enter settlement. A sender that rejects ETH
            // keeps the surplus here rather than reverting a batch the skip exists to protect.
            (bool refunded,) = msg.sender.call{value: msg.value - required}("");
            refunded;
        }
    }

    /// @dev The single-transition settlement path shared by both entrypoints. Callers must
    ///      hold the `guardTransition` latch.
    function _verifyAndUpdateOne(
        bytes32 msgHash,
        uint32 referenceBlockNumber,
        bytes calldata storageUpdates,
        uint256 transitionIndex,
        bytes4 targetFunction,
        uint256 value,
        uint256 s,
        address Raddr,
        address[] calldata nonSigners
    ) private trackState {
        require(referenceBlockNumber < block.number, FutureBlockNumber());
        require((uint256(referenceBlockNumber) + _getBlockStaleMeasure()) >= block.number, StaleBlockNumber());

        require(transitionIndex + 1 == stateTransitionCount(), InvalidTransitionIndex());
        require(_digest(transitionIndex, targetFunction, storageUpdates, value) == msgHash, InvalidSignature());

        _verifyQuorum(msgHash, s, Raddr, nonSigners, referenceBlockNumber);

        _stateChangeHandler(storageUpdates);
    }

    function _verifyQuorum(
        bytes32 msgHash,
        uint256 s,
        address Raddr,
        address[] calldata nonSigners,
        uint32 referenceBlockNumber
    ) private view {
        bool ok = _schnorrRegistry().isValidSignature(msgHash, s, Raddr, nonSigners, referenceBlockNumber);
        require(ok, InvalidQuorumSignature());
    }

    function _stateChangeHandler(bytes calldata storageUpdates) internal {
        (StateUpdateType[] memory types, bytes[] memory args) = abi.decode(storageUpdates, (StateUpdateType[], bytes[]));
        StateChangeHandlerLib._runStateUpdates(types, args);
    }

    /// @notice Query if a contract implements an interface
    /// @dev Supports ERC-165, IGasKillerSDK detection (the router's preflight
    ///      probes the schnorr `verifyAndUpdate` selector before submitting), and the
    ///      IGasKillerSDKBatch batching/latch extension. Defers to `super` so a
    ///      contract inheriting both this SDK and another OpenZeppelin ERC-165 module reports
    ///      the union of both ID sets.
    /// @param interfaceId The interface identifier, as specified in ERC-165
    /// @return `true` if the contract implements `interfaceId` and `false` otherwise
    function supportsInterface(bytes4 interfaceId) public view virtual override(ERC165, IERC165) returns (bool) {
        return interfaceId == type(IGasKillerSDK).interfaceId || interfaceId == type(IGasKillerSDKBatch).interfaceId
            || interfaceId == type(IGasKillerValueBound).interfaceId || super.supportsInterface(interfaceId);
    }

    /// @notice Compute the expected message hash for a transition settled with no ETH
    /// @dev Exact mirror of the ECDSA `GasKillerSDK.getMessageHash` — the digest is
    ///      scheme-agnostic, so off-chain parity checks work unchanged.
    /// @param transitionIndex The transition index
    /// @param targetFunction The target function selector
    /// @param storageUpdates The ABI-encoded storage updates
    /// @return The expected SHA-256 hash
    function getMessageHash(uint256 transitionIndex, bytes4 targetFunction, bytes calldata storageUpdates)
        external
        view
        returns (bytes32)
    {
        return _digest(transitionIndex, targetFunction, storageUpdates, 0);
    }

    /// @notice Compute the expected message hash for a transition settled with `value` wei
    /// @dev Named apart from `getMessageHash` because an overload would rename the generated
    ///      off-chain binding of the existing function.
    /// @param transitionIndex The transition index
    /// @param targetFunction The target function selector
    /// @param storageUpdates The ABI-encoded storage updates
    /// @param value The `msg.value` the transition settles with
    /// @return The expected SHA-256 hash
    function getMessageHashWithValue(
        uint256 transitionIndex,
        bytes4 targetFunction,
        bytes calldata storageUpdates,
        uint256 value
    ) external view returns (bytes32) {
        return _digest(transitionIndex, targetFunction, storageUpdates, value);
    }

    /// @dev Mirrored by `NestedFrames.rootLeaf`, which must stay byte-identical.
    function _digest(uint256 transitionIndex, bytes4 targetFunction, bytes calldata storageUpdates, uint256 value)
        private
        view
        returns (bytes32)
    {
        if (value == 0) return sha256(abi.encode(transitionIndex, address(this), targetFunction, storageUpdates));
        return sha256(abi.encode(transitionIndex, address(this), targetFunction, storageUpdates, value));
    }

    /// @inheritdoc TransitionGuard
    function inTransition() public view override(TransitionGuard, IGasKillerSDKBatch) returns (bool locked) {
        return TransitionGuard.inTransition();
    }

    function schnorrRegistry() external view returns (address) {
        return address(_schnorrRegistry());
    }

    function avsAddress() external view returns (address) {
        return _sto().avsAddress;
    }

    function blockStaleMeasure() external view returns (uint256) {
        return _getBlockStaleMeasure();
    }

    function _setAvsAddress(address _avsAddress) internal {
        _sto().avsAddress = _avsAddress;
    }

    function _setSchnorrRegistry(address _registry) internal {
        _sto().registry = ISchnorrStakeRegistry(_registry);
    }

    function _schnorrRegistry() internal view returns (ISchnorrStakeRegistry) {
        return _sto().registry;
    }

    function _setBlockStaleMeasure(uint256 _blockStaleMeasure) internal {
        require(_blockStaleMeasure <= type(uint96).max, BlockStaleMeasureOverflow());
        _sto().blockStaleMeasure = uint96(_blockStaleMeasure);
    }

    function _getBlockStaleMeasure() internal view returns (uint256) {
        uint256 v = _sto().blockStaleMeasure;
        return v == 0 ? DEFAULT_BLOCK_STALE_MEASURE : v;
    }

    function _sto() private pure returns (GasKillerSDKStorage storage $) {
        assembly {
            $.slot := STORAGE_LOCATION
        }
    }
}
