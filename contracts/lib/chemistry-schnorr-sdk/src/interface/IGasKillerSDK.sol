// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity ^0.8.27;

import {IERC165} from "../../oz/utils/introspection/IERC165.sol";

/// @title IGasKillerSDK
/// @notice Interface for GasKillerSDK contracts
/// @dev Defines the core functionality that GasKillerSDK implementations must
///      provide. State updates are approved by an operator quorum expressed as a
///      **single** aggregate Schnorr signature verified by a `SchnorrStakeRegistry`
///      (constant gas, non-signer subtraction) instead of `N` per-operator ECDSA
///      signatures. Deliberately single-function so
///      `type(IGasKillerSDK).interfaceId` equals the `verifyAndUpdate`
///      selector — the router's ERC-165 preflight probes exactly this ID.
interface IGasKillerSDK is IERC165 {
    /// @notice Verify the operators' aggregate Schnorr quorum signature and apply the
    ///         encoded state updates
    /// @dev Payable, and `msg.value` is part of the signed digest: the transition settles only
    ///      with exactly the value the task was analyzed with, so a function that credits
    ///      `msg.value` cannot be settled without its ETH. Value moved by state updates is fixed
    ///      inside the signed `storageUpdates`; a shortfall reverts the whole transition.
    ///
    ///      `payable` does not change the function selector, so
    ///      `type(IGasKillerSDK).interfaceId` — which the router's ERC-165 preflight
    ///      probes — is unaffected.
    /// @param msgHash The hash of the message to verify (sha256 of the encoded task)
    /// @param referenceBlockNumber The block number at which operator keys and stake
    ///        weights are evaluated by the stake registry
    /// @param storageUpdates The storage updates to verify and apply
    /// @param transitionIndex The transition index
    /// @param targetFunction The target function selector
    /// @param s Aggregate Schnorr response scalar
    /// @param Raddr Aggregate nonce address `address(R)`
    /// @param nonSigners Operators that did not sign, in strictly ascending order
    function verifyAndUpdate(
        bytes32 msgHash,
        uint32 referenceBlockNumber,
        bytes calldata storageUpdates,
        uint256 transitionIndex,
        bytes4 targetFunction,
        uint256 s,
        address Raddr,
        address[] calldata nonSigners
    ) external payable;
}
