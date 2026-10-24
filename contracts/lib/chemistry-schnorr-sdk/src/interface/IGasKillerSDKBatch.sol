// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity ^0.8.27;

/// @notice One independently quorum-signed state transition, as submitted to
///         `verifyAndUpdateBatch`. The arguments of `IGasKillerSDK.verifyAndUpdate` plus the
///         `value` it would have been sent with, so the signed digest is the same either way
///         and the off-chain signing path does not know or care whether a transition settles
///         alone or in a batch.
struct TaskSubmission {
    bytes32 msgHash;
    uint32 referenceBlockNumber;
    bytes storageUpdates;
    uint256 transitionIndex;
    bytes4 targetFunction;
    uint256 s;
    address Raddr;
    address[] nonSigners;
    uint256 value;
}

/// @title IGasKillerSDKBatch
/// @notice Optional batching + in-transition-latch extension of `IGasKillerSDK`.
/// @dev Kept separate from `IGasKillerSDK` on purpose: that interface is
///      deliberately single-function so `type(IGasKillerSDK).interfaceId` equals
///      the `verifyAndUpdate` selector, which the router's ERC-165 preflight probes.
///      Contracts supporting this extension report **both** interface IDs.
///
///      Batching amortizes the per-transaction fixed costs across N transitions: the
///      21,000 intrinsic, the cold-access warm-up of the registry account + its aggregate
///      key/weight/watermark slots, and the SDK's own config slots — everything after the
///      first sub-transition runs at warm-access prices (measured: the registry verify
///      alone drops from ~17.0k cold to ~6.5k warm at full participation).
///
///      Batch assemblers (the off-chain router composing `submissions`) should be aware
///      that `StateChangeHandlerLib`'s `CALL` update forwards *all* remaining gas to its
///      target with no cap. A greedy or griefing CALL target in an early sub-transition can
///      consume enough gas to starve every later sub-transition, reverting the whole
///      (atomic) batch — no partial-state hazard, since it's all-or-nothing, but it does
///      nullify the amortization this extension exists for. Ordering submissions with
///      untrusted CALL targets last, or excluding them from batches entirely, avoids this.
interface IGasKillerSDKBatch {
    /// @notice Verify and apply a sequence of independently signed state transitions.
    /// @dev Transitions apply in calldata order with consecutive `transitionIndex`es.
    ///      Submissions whose index is already settled are skipped (front-run/redelivery
    ///      tolerance — settlement is permissionless, so without the skip one lifted
    ///      submission settled standalone would revert the whole batch); an index gap or
    ///      any failing applied sub-transition reverts the whole batch. The in-transition
    ///      latch is held across the entire batch.
    ///
    ///      Payable. Each submission's digest binds its own `value`, and `msg.value` must cover
    ///      the sum over the submissions actually applied. A skipped (already-settled)
    ///      submission adds nothing to that sum. The surplus, such as a front-run item's
    ///      share, is refunded to `msg.sender`; a sender that can't accept ETH leaves it in
    ///      the contract instead of reverting the batch.
    /// @param submissions The transitions to apply, in order.
    function verifyAndUpdateBatch(TaskSubmission[] calldata submissions) external payable;

    /// @notice True while a state transition (or batch) is being applied — external
    ///         readers should treat mid-transition state as unsigned and fail closed.
    function inTransition() external view returns (bool);
}
