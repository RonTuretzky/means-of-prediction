// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {EmailProof} from "./IDKIMVerifier.sol";
import {HeadlineMarket} from "../market/HeadlineMarket.sol";

/// @dev Immutable data-only runtime. The leading STOP makes arbitrary email bytes
/// non-executable; deployed code cannot call out or self-destruct.
contract EmailBodyChunk {
    constructor(bytes memory data) {
        bytes memory runtime = bytes.concat(hex"00", data);
        assembly ("memory-safe") { return(add(runtime, 32), mload(runtime)) }
    }
}

/// @notice Permissionless paginated email transport. Stores <=24,000-byte pages in
/// immutable contract code, then assembles the full canonical body for the existing
/// verifier/market. Storage is NOT authentication: the final RSA + bh= verification
/// still decides whether these pages are the newspaper's signed body.
contract EmailBodyStore {
    uint256 public constant MAX_CHUNK_BYTES = 24000;
    uint256 public constant MAX_BODY_BYTES = 196608;
    uint256 public constant MAX_CHUNKS = 9;
    mapping(bytes32 => address) public chunkForHash;
    mapping(address => uint256) public chunkLength;
    event BodyChunkStored(bytes32 indexed chunkHash, address indexed pointer, uint256 length);

    function storeChunk(bytes calldata data) external returns (address pointer) {
        require(data.length > 0 && data.length <= MAX_CHUNK_BYTES, "BodyStore: invalid chunk size");
        bytes32 hash = keccak256(data);
        pointer = chunkForHash[hash];
        if (pointer != address(0)) return pointer;
        pointer = address(new EmailBodyChunk(data));
        chunkForHash[hash] = pointer;
        chunkLength[pointer] = data.length;
        emit BodyChunkStored(hash, pointer, data.length);
    }

    function assemble(address[] calldata pointers) public view returns (bytes memory body) {
        require(pointers.length > 0 && pointers.length <= MAX_CHUNKS, "BodyStore: invalid chunk count");
        uint256 total;
        for (uint256 i; i < pointers.length; ++i) {
            uint256 length = chunkLength[pointers[i]];
            require(length > 0, "BodyStore: unknown chunk");
            total += length;
        }
        require(total <= MAX_BODY_BYTES, "BodyStore: body too large");
        body = new bytes(total);
        uint256 offset;
        for (uint256 i; i < pointers.length; ++i) {
            address pointer = pointers[i];
            uint256 length = chunkLength[pointer];
            assembly ("memory-safe") { extcodecopy(pointer, add(add(body, 32), offset), 1, length) }
            offset += length;
        }
    }

    function checkWithChunks(address market, uint256 sourceIndex, EmailProof calldata proof, address[] calldata pointers)
        external view returns (bool ok, string memory reason)
    {
        EmailProof memory expanded = expand(proof, pointers);
        return HeadlineMarket(market).checkProof(sourceIndex, expanded);
    }

    function submitWithChunks(address market, uint256 sourceIndex, EmailProof calldata proof, address[] calldata pointers)
        external
    {
        EmailProof memory expanded = expand(proof, pointers);
        HeadlineMarket(market).submitProof(sourceIndex, expanded);
    }

    function expand(EmailProof calldata proof, address[] calldata pointers) private view returns (EmailProof memory expanded) {
        require(proof.canonicalBody.length == 0, "BodyStore: body must be supplied by chunks");
        expanded = proof;
        expanded.canonicalBody = assemble(pointers);
    }
}
