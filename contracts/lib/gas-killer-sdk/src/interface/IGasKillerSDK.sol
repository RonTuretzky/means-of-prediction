// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity ^0.8.0;

import {IERC165} from "forge-std/interfaces/IERC165.sol";
import {IBLSSignatureCheckerTypes} from "@eigenlayer-middleware/interfaces/IBLSSignatureChecker.sol";

/// @title IGasKillerSDK
/// @notice Interface for GasKillerSDK contracts
/// @dev Defines the core functionality that GasKillerSDK implementations must provide
interface IGasKillerSDK is IERC165 {
    // Custom errors

    /// @notice Thrown when `transitionIndex + 1` does not equal the current `stateTransitionCount`
    error InvalidTransitionIndex();

    /// @notice Thrown when the reconstructed message hash does not match `msgHash`
    error InvalidSignature();

    /// @notice Thrown when the provided storage updates cannot be decoded or applied
    error InvalidStorageUpdates();

    /// @notice Thrown when an unrecognised state update operation type is encountered
    error InvalidOperation();

    /// @notice Thrown when signatories hold less than `QUORUM_THRESHOLD`% of stake for any quorum
    error InsufficientQuorumThreshold();

    /// @notice Thrown when `referenceBlockNumber` is older than `blockStaleMeasure` blocks ago
    error StaleBlockNumber();

    /// @notice Thrown when `referenceBlockNumber` is greater than or equal to the current block number
    error FutureBlockNumber();

    /// @notice Verify BLS quorum signatures and apply the encoded state updates
    /// @dev Payable so a caller can fund value-bearing `CALL`/`CREATE`/`CREATE2` state updates
    ///      out of `msg.value`. The value each update moves is fixed inside the quorum-signed
    ///      `storageUpdates`, so `msg.value` only tops up the contract's balance — it cannot
    ///      redirect value anywhere the quorum did not sign. Under-funding reverts the whole
    ///      transition. Over-funding is NOT refunded: whatever the updates do not consume stays
    ///      in the contract, and recovering it is the responsibility of the inheriting contract
    ///      (e.g. a withdrawal function, or a refund executed as a signed CALL update in a
    ///      later transition).
    /// @param msgHash The hash of the message to verify
    /// @param quorumNumbers The quorum numbers to check signatures for
    /// @param referenceBlockNumber The block number to use as reference for operator set
    /// @param storageUpdates The storage updates to verify
    /// @param transitionIndex The transition index
    /// @param targetFunction The target function selector
    /// @param nonSignerStakesAndSignature The non-signer stakes and signature data computed off-chain
    function verifyAndUpdate(
        bytes32 msgHash,
        bytes calldata quorumNumbers,
        uint32 referenceBlockNumber,
        bytes calldata storageUpdates,
        uint256 transitionIndex,
        bytes4 targetFunction,
        IBLSSignatureCheckerTypes.NonSignerStakesAndSignature calldata nonSignerStakesAndSignature
    ) external payable;
}
