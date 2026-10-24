// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity ^0.8.27;

import {QuorumSignature} from "./ISchnorrApprovalRegistry.sol";

/// @notice Everything the root contract needs to settle a nested tree.
/// @param root            the signed Merkle root.
/// @param expiryBlock     the last block at which the tree may settle.
/// @param expiryProof     Merkle proof of the expiry leaf.
/// @param sig             the quorum signature over `root`.
/// @param transitionIndex expected `stateTransitionCount() - 1` of the root contract.
/// @param targetFunction  selector bound into the root leaf.
/// @param storageUpdates  the root frame's program.
/// @param proof           Merkle proof of the root leaf.
/// @param children        one `abi.encode(NestedFrames.Witness)` per `NESTED` op in the root
///                        frame's program, in program order.
struct TreeSubmission {
    bytes32 root;
    uint256 expiryBlock;
    bytes32[] expiryProof;
    QuorumSignature sig;
    uint256 transitionIndex;
    bytes4 targetFunction;
    bytes storageUpdates;
    bytes32[] proof;
    bytes[] children;
}

/// @title IGasKillerNested
/// @notice Nested settlement: one quorum signature over a Merkle root authorizes a tree of
///         frames across SDK-enabled contracts, each applied by the contract it belongs to.
/// @dev An ERC-165 extension separate from `IGasKillerSDK`, whose interface ID must stay equal
///      to the `verifyAndUpdate` selector the router probes.
interface IGasKillerNested {
    error NotApproved(bytes32 root);
    error LeafMismatch(bytes32 expected, bytes32 computed);
    error NotPendingChild(address parent, bytes32 leaf);
    error NotTreeMember(bytes32 leaf);

    /// @notice Settle a tree whose root frame belongs to this contract.
    function verifyAndUpdateTree(TreeSubmission calldata submission) external payable;

    /// @notice Apply this contract's frame of an approved tree. Called by the frame's signed
    ///         parent while it executes the `NESTED` op that names this frame.
    /// @param root         the approved root.
    /// @param expectedLeaf the leaf hash the parent's signed program names.
    /// @param witness      `abi.encode(NestedFrames.Witness)` for this frame.
    /// @return             `applyNested.selector`; the parent rejects any other return.
    function applyNested(bytes32 root, bytes32 expectedLeaf, bytes calldata witness) external payable returns (bytes4);

    /// @notice The leaf of the child this contract is calling right now, or zero.
    function pendingChild() external view returns (bytes32);
}
