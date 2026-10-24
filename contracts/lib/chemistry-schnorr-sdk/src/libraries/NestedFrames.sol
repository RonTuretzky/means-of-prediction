// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity ^0.8.27;

import {MerkleProof} from "../../oz/utils/cryptography/MerkleProof.sol";

/// @title NestedFrames
/// @notice Leaf hashing, tree membership and witness decoding for nested settlement, where
///         one quorum signature over a Merkle root authorizes every frame of a call tree.
/// @dev A tree's leaves are an expiry leaf followed by one leaf per frame in execution order.
///      Internal nodes use OpenZeppelin's sorted-pair keccak. Every leaf is a sha256 digest
///      computed here from typed fields, so callers never hand in a leaf hash and an internal
///      node can never be presented as a leaf.
///
///      Three leaf types:
///        - root leaf:   the single-transition digest, value included, so a consumer settled
///                       without nesting signs exactly what it signs for `verifyAndUpdate`;
///        - nested leaf: a callee frame, binding chain, contract, caller, value and index;
///        - expiry leaf: the block after which neither the root nor any frame may settle.
///      The nested and expiry tags are keccak-derived words in the first slot of their
///      preimages, where the root leaf carries a transition index, so no preimage of one type
///      can equal a preimage of another.
library NestedFrames {
    /// keccak256("gaskiller.nested.leaf.v1")
    bytes32 internal constant NESTED_LEAF_TAG = 0x292ca629b989c44a85e556e7c24acc26f9ab093b2b23c689f951e91718228c18;
    /// keccak256("gaskiller.nested.expiry.v1")
    bytes32 internal constant EXPIRY_LEAF_TAG = 0xc5763e3656f5ee85e7416218ca476fe6364ba9f67d13b29c7331d1d1131dd88a;

    /// @notice The only frame mode this build accepts: transition-counter pinning.
    /// @dev Compiled in, never read from a witness, so a contract built before a new mode
    ///      cannot be made to accept leaves signed for it.
    uint8 internal constant MODE = 0;

    /// @notice The unsigned data a parent passes to a child alongside the child's leaf hash.
    /// @dev `children` are opaque `abi.encode(Witness)` blobs because the ABI cannot express a
    ///      recursive struct. Everything here is authenticated through the leaf and the proof;
    ///      `calldataHash` is recorded for fraud proofs and re-derived by nothing on-chain.
    struct Witness {
        bytes32 calldataHash;
        bytes storageUpdates;
        bytes32[] proof;
        bytes[] children;
    }

    /// @dev Must stay byte-identical to `GasKillerSDK`'s digest, zero-value encoding included.
    function rootLeaf(
        uint256 transitionIndex,
        address target,
        bytes4 targetFunction,
        bytes memory storageUpdates,
        uint256 value
    ) internal pure returns (bytes32) {
        if (value == 0) {
            return sha256(abi.encode(transitionIndex, target, targetFunction, storageUpdates));
        }
        return sha256(abi.encode(transitionIndex, target, targetFunction, storageUpdates, value));
    }

    function nestedLeaf(
        address target,
        uint256 transitionIndex,
        address caller,
        uint256 value,
        bytes32 calldataHash,
        bytes memory storageUpdates
    ) internal view returns (bytes32) {
        return sha256(
            abi.encode(
                NESTED_LEAF_TAG,
                block.chainid,
                target,
                transitionIndex,
                caller,
                value,
                calldataHash,
                MODE,
                storageUpdates
            )
        );
    }

    function expiryLeaf(address rootContract, uint256 expiryBlock) internal view returns (bytes32) {
        return sha256(abi.encode(EXPIRY_LEAF_TAG, block.chainid, rootContract, expiryBlock));
    }

    function isMember(bytes32[] memory proof, bytes32 root, bytes32 leaf) internal pure returns (bool) {
        return MerkleProof.verify(proof, root, leaf);
    }

    function isMemberCalldata(bytes32[] calldata proof, bytes32 root, bytes32 leaf) internal pure returns (bool) {
        return MerkleProof.verifyCalldata(proof, root, leaf);
    }

    /// @dev `abi.decode` bounds-checks every offset and length, so a malformed witness reverts
    ///      rather than decoding garbage.
    function decodeWitness(bytes memory encoded) internal pure returns (Witness memory) {
        return abi.decode(encoded, (Witness));
    }
}
