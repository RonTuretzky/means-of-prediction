// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

contract PeaceFinalizeDataShard {
    constructor(bytes memory data) {
        bytes memory runtime = bytes.concat(hex"00", data);
        assembly ("memory-safe") { return(add(runtime, 32), mload(runtime)) }
    }
}

/// @notice Sealed exact calldata transport; never substitutes for evidence verification.
/// @dev Publication/setup costs are separate. Staging avoids oversized constructor initcode.
contract PeaceFinalizePacketCache {
    uint256 public constant MAX_CHUNK_BYTES = 24575;
    bytes32 public immutable packetHash;
    uint256 public immutable packetLength;
    address public immutable builder;
    address[] public shards;
    bytes32[] public shardCodeHashes;
    uint256 public writtenBytes;
    bool public isSealed;
    bytes32 public manifestHash;
    error NotBuilder(); error AlreadySealed(); error BadChunk(); error BadPacket(); error NotSealed(); error ShardChanged();

    constructor(bytes32 expectedHash, uint256 expectedLength, address builder_) {
        if (expectedHash == 0 || expectedLength == 0 || expectedLength > 1_048_576 || builder_ == address(0)) revert BadPacket();
        packetHash = expectedHash; packetLength = expectedLength; builder = builder_;
    }
    function appendChunk(bytes calldata chunk) external {
        if (msg.sender != builder) revert NotBuilder();
        if (isSealed) revert AlreadySealed();
        if (chunk.length == 0 || chunk.length > MAX_CHUNK_BYTES || writtenBytes + chunk.length > packetLength) revert BadChunk();
        address shard = address(new PeaceFinalizeDataShard(chunk));
        shards.push(shard); shardCodeHashes.push(shard.codehash); writtenBytes += chunk.length;
    }
    function seal() external {
        if (msg.sender != builder) revert NotBuilder();
        if (isSealed) revert AlreadySealed();
        if (writtenBytes != packetLength || keccak256(_read()) != packetHash) revert BadPacket();
        manifestHash = keccak256(abi.encode(packetHash, packetLength, shards, shardCodeHashes));
        isSealed = true;
    }
    function shardCount() external view returns (uint256) { return shards.length; }
    function read() external view returns (bytes memory packet) {
        if (!isSealed) revert NotSealed();
        packet = _read();
        if (keccak256(packet) != packetHash) revert BadPacket();
    }
    function _read() private view returns (bytes memory packet) {
        packet = new bytes(writtenBytes);
        uint256 offset;
        for (uint256 i; i < shards.length; ++i) {
            address shard = shards[i];
            if (shard.codehash != shardCodeHashes[i] || shard.code.length < 2) revert ShardChanged();
            uint256 size = shard.code.length - 1;
            if (offset + size > packet.length) revert BadPacket();
            assembly ("memory-safe") { extcodecopy(shard, add(add(packet, 32), offset), 1, size) }
            offset += size;
        }
        if (offset != packet.length) revert BadPacket();
    }
}
