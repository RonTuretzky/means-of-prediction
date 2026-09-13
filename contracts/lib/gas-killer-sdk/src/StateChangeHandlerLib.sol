// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity ^0.8.0;

/// @notice Discriminator enum for the type of state update operation to execute
/// @dev Each variant maps to a different EVM operation: storage writes, external calls, log emissions, or contract deployment
enum StateUpdateType {
    /// @notice Write a 32-byte value directly to a storage slot
    STORE,
    /// @notice Execute an external call with optional ETH value transfer
    CALL,
    /// @notice Emit a log with no indexed topics
    LOG0,
    /// @notice Emit a log with one indexed topic
    LOG1,
    /// @notice Emit a log with two indexed topics
    LOG2,
    /// @notice Emit a log with three indexed topics
    LOG3,
    /// @notice Emit a log with four indexed topics
    LOG4,
    /// @notice Deploy a contract using CREATE (nonce-derived address)
    CREATE,
    /// @notice Deploy a contract using CREATE2 (salt-derived deterministic address)
    CREATE2
}

/// @title StateChangeHandlerLib
/// @notice Library for decoding and executing batched state update operations
/// @dev Processes ABI-encoded arrays of typed state updates; supports STORE, CALL, LOG0-LOG4, CREATE, and CREATE2
library StateChangeHandlerLib {
    /// @notice Decodes and executes a series of state updates
    /// @dev This function processes an array of state updates, executing them in sequence. Each update can be one of:
    ///      - STORE: Direct storage writes using assembly
    ///      - CALL: External contract calls with value transfer
    ///      - LOG0-LOG4: Event emission with 0-4 indexed topics
    ///      - CREATE: Contract deployment via CREATE opcode
    ///      - CREATE2: Deterministic contract deployment via CREATE2 opcode
    /// @param types Array of StateUpdateType enums indicating the type of each state update operation
    /// @param args Array of ABI-encoded arguments corresponding to each operation type
    /// @dev types and args arrays must be equal length, with args[i] containing the encoded parameters for types[i]
    function _runStateUpdates(StateUpdateType[] memory types, bytes[] memory args) internal {
        uint256 length = types.length;
        require(length == args.length, InvalidArguments());
        for (uint256 i = 0; i < length; ++i) {
            StateUpdateType stateUpdateType = types[i];
            bytes memory arg = args[i];

            if (stateUpdateType == StateUpdateType.STORE) {
                (bytes32 slot, bytes32 value) = abi.decode(arg, (bytes32, bytes32));
                assembly {
                    sstore(slot, value)
                }
            } else if (stateUpdateType == StateUpdateType.CALL) {
                // Forwards all remaining gas (no stipend cap). In a batched settlement
                // (e.g. SchnorrGasKillerSDK.verifyAndUpdateBatch) this is amplified: a
                // greedy or griefing target in an earlier sub-transition's CALL can consume
                // enough gas to starve every later sub-transition in the same batch,
                // reverting the whole (atomic) batch. No partial-state hazard — it's all or
                // nothing — but it does nullify the batch's cost amortization. See
                // ISchnorrGasKillerSDKBatch for the batch-assembly-side note.
                (address target, uint256 value, bytes memory callargs) = abi.decode(arg, (address, uint256, bytes));
                bool success;
                assembly {
                    success := call(gas(), target, value, add(callargs, 0x20), mload(callargs), 0, 0)
                }
                // TODO: this section needs heavy testing
                if (!success) {
                    uint256 _returndatasize;
                    assembly {
                        _returndatasize := returndatasize()
                    }
                    bytes memory revertData = new bytes(_returndatasize);
                    assembly {
                        returndatacopy(add(revertData, 0x20), 0, _returndatasize)
                    }
                    revert RevertingContext(i, target, revertData, callargs);
                }
            } else if (stateUpdateType == StateUpdateType.LOG0) {
                // `_validateLogArg` checks that `arg` is a canonical, in-bounds encoding before this reads
                // directly out of its buffer. The `data` length word sits at `base + canonicalOffset`, and
                // any topics sit inline in the head at `base + 0x20*k`.
                _validateLogArg(arg, 0x20);
                assembly {
                    let dataPtr := add(add(arg, 0x20), 0x20)
                    log0(add(dataPtr, 0x20), mload(dataPtr))
                }
            } else if (stateUpdateType == StateUpdateType.LOG1) {
                _validateLogArg(arg, 0x40);
                assembly {
                    let base := add(arg, 0x20)
                    let dataPtr := add(base, 0x40)
                    log1(add(dataPtr, 0x20), mload(dataPtr), mload(add(base, 0x20)))
                }
            } else if (stateUpdateType == StateUpdateType.LOG2) {
                _validateLogArg(arg, 0x60);
                assembly {
                    let base := add(arg, 0x20)
                    let dataPtr := add(base, 0x60)
                    log2(add(dataPtr, 0x20), mload(dataPtr), mload(add(base, 0x20)), mload(add(base, 0x40)))
                }
            } else if (stateUpdateType == StateUpdateType.LOG3) {
                _validateLogArg(arg, 0x80);
                assembly {
                    let base := add(arg, 0x20)
                    let dataPtr := add(base, 0x80)
                    log3(
                        add(dataPtr, 0x20),
                        mload(dataPtr),
                        mload(add(base, 0x20)),
                        mload(add(base, 0x40)),
                        mload(add(base, 0x60))
                    )
                }
            } else if (stateUpdateType == StateUpdateType.LOG4) {
                _validateLogArg(arg, 0xa0);
                assembly {
                    let base := add(arg, 0x20)
                    let dataPtr := add(base, 0xa0)
                    log4(
                        add(dataPtr, 0x20),
                        mload(dataPtr),
                        mload(add(base, 0x20)),
                        mload(add(base, 0x40)),
                        mload(add(base, 0x60)),
                        mload(add(base, 0x80))
                    )
                }
            } else if (stateUpdateType == StateUpdateType.CREATE) {
                (uint256 value, bytes memory initcode) = abi.decode(arg, (uint256, bytes));
                address deployed;
                assembly {
                    deployed := create(value, add(initcode, 0x20), mload(initcode))
                }
                require(deployed != address(0), DeploymentFailed());
            } else if (stateUpdateType == StateUpdateType.CREATE2) {
                (bytes32 salt, uint256 value, bytes memory initcode) = abi.decode(arg, (bytes32, uint256, bytes));
                address deployed;
                assembly {
                    deployed := create2(value, add(initcode, 0x20), mload(initcode), salt)
                }
                require(deployed != address(0), DeploymentFailed());
            }
        }
    }

    /// @notice Validate that `arg` is a canonical, in-bounds ABI encoding of a LOG payload
    /// @dev Reverts with `MalformedLogPayload` on a truncated head, a non-canonical `data` offset, or a
    ///      `data` length that runs past the end of `arg`. `canonicalOffset` is the encoding's head size
    ///      `0x20 * (numTopics + 1)` (0x20 for LOG0, 0x40 for LOG1, ... 0xa0 for LOG4); it is also where the
    ///      `data` length word lives, and every fixed `bytes32` topic sits within the head before it.
    /// @param arg The ABI-encoded LOG payload to validate
    /// @param canonicalOffset The expected offset of the `data` field (equals the encoding's head size)
    function _validateLogArg(bytes memory arg, uint256 canonicalOffset) private pure {
        uint256 len = arg.length;
        // The head (offset word + topics) and the `data` length word must both be readable.
        if (len < canonicalOffset + 0x20) revert MalformedLogPayload();
        uint256 off;
        uint256 dataLen;
        assembly {
            let base := add(arg, 0x20)
            off := mload(base)
            dataLen := mload(add(base, canonicalOffset))
        }
        // Offset must match what abi.encode produces, and the data bytes must fit inside `arg`.
        // `len >= canonicalOffset + 0x20` above makes the subtraction below safe.
        if (off != canonicalOffset) revert MalformedLogPayload();
        if (dataLen > len - canonicalOffset - 0x20) revert MalformedLogPayload();
    }

    /// @notice Thrown when `types` and `args` arrays have different lengths
    error InvalidArguments();

    /// @notice Thrown when a LOG operation's payload is not a canonical, in-bounds ABI encoding
    error MalformedLogPayload();

    /// @notice Thrown when a CALL operation's external call reverts
    /// @param index The zero-based position of the failing operation in the batch
    /// @param target The contract address that was called
    /// @param revertData The raw revert data returned by the failed call
    /// @param callargs The calldata that was passed to the failed call
    error RevertingContext(uint256 index, address target, bytes revertData, bytes callargs);

    /// @notice Thrown when a CREATE or CREATE2 operation returns address(0)
    error DeploymentFailed();
}
