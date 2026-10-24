// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity ^0.8.27;

/// @title TransitionGuard
/// @notice EIP-1153 transient-storage reentrancy guard that doubles as an
///         "in transition" latch external contracts can query.
/// @dev Two holes in the unguarded settlement path, one mechanism:
///
///      1. **Reentrancy.** `StateChangeHandlerLib`'s `CALL` update forwards all remaining
///         gas to an arbitrary target *mid-transition* — after `trackState` has already
///         bumped the counter and before the transition's later updates have executed. A
///         re-entrant `verifyAndUpdate` carrying transition N+1's valid quorum signature
///         would pass the transition-index check and interleave N+1's updates inside N.
///         `guardTransition` makes the re-entrant call revert instead.
///
///      2. **Midway state.** During a `CALL` update the called contract observes storage
///         that never existed per the signed semantics: the transition counter already
///         shows N+1 while only a prefix of transition N's updates have landed. The quorum
///         signed the *final* post-transition state, not this intermediate one. The same
///         transient flag is exposed as `inTransition()`, so integrators reading a Gas
///         Killer contract can fail closed (revert or fall back) while a transition is
///         being applied, for one warm TLOAD (~100 gas) paid by the reader.
///
///      Transient storage clears automatically at the end of the transaction, so the
///      guard costs ~3 transient ops (~300 gas) per guarded call and never leaves a
///      dirty storage slot behind. Requires an EVM with EIP-1153 (Cancun or later).
///
///      The slot holds the active nested-settlement root rather than a flag, so a call tree
///      that re-enters this contract (A → B → A) can apply its second frame here while every
///      other re-entry still reverts. Single-transition and batch settlement hold
///      `EXCLUSIVE_MARKER`, a value no root (a hash output) can take.
abstract contract TransitionGuard {
    /// @notice Precomputed transient-storage slot for the guard flag
    /// @dev Computed as `keccak256("gasKiller.transitionGuard") - 1`, mirroring
    ///      `StateTracker`'s slot-derivation convention.
    bytes32 internal constant TRANSITION_GUARD_SLOT =
        0x577f51c71236185614d2425ce0aefc41d4e67f3a91a20821f72674b76f8d3ec0;

    bytes32 internal constant EXCLUSIVE_MARKER = bytes32(uint256(1));

    /// @notice Thrown when a guarded function is re-entered while a transition is applying
    error ReentrantTransition();

    /// @notice Reverts on re-entry and holds the in-transition latch for the duration of
    ///         the function body (a batch entrypoint holds it across the whole batch).
    modifier guardTransition() {
        _enterExclusive(EXCLUSIVE_MARKER);
        _;
        _exitTransition(bytes32(0));
    }

    /// @notice True while a state transition (or batch of transitions) is being applied
    /// @dev External contracts that read Gas Killer state and can be called mid-transition
    ///      (directly or transitively via a `CALL` update) should check this and fail
    ///      closed — mid-transition storage is not a quorum-signed state.
    function inTransition() public view virtual returns (bool locked) {
        return _activeRoot() != bytes32(0);
    }

    function _activeRoot() internal view returns (bytes32 root) {
        assembly {
            root := tload(TRANSITION_GUARD_SLOT)
        }
    }

    /// @dev For entrypoints that start a transition: reverts if any transition is applying.
    function _enterExclusive(bytes32 root) internal {
        if (_activeRoot() != bytes32(0)) revert ReentrantTransition();
        _setActiveRoot(root);
    }

    /// @dev For a nested frame: allowed when idle, or when re-entered by a frame of the same
    ///      root. Returns the value to restore on exit, so an inner frame of a cycle leaves the
    ///      outer frame's latch in place.
    function _enterNested(bytes32 root) internal returns (bytes32 previous) {
        previous = _activeRoot();
        if (previous != bytes32(0) && previous != root) revert ReentrantTransition();
        _setActiveRoot(root);
    }

    function _exitTransition(bytes32 previous) internal {
        _setActiveRoot(previous);
    }

    function _setActiveRoot(bytes32 root) private {
        assembly {
            tstore(TRANSITION_GUARD_SLOT, root)
        }
    }
}
