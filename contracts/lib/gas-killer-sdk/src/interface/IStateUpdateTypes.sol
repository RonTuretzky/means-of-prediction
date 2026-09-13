// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity ^0.8.0;

/// @title IStateUpdateTypes
/// @notice Typed structs representing each `StateUpdateType` operation payload
/// @dev Only relevant for off-chain ABI consumers (e.g. alloy); mirrors the encoding
///      expected by `StateChangeHandlerLib._runStateUpdates`
// NOTE: only relevant for alloy
interface IStateUpdateTypes {
    /// @notice Payload for a STORE operation — write `value` to `slot`
    struct Store {
        /// @notice The 32-byte storage slot to write to
        bytes32 slot;
        /// @notice The 32-byte value to write into the slot
        bytes32 value;
    }

    /// @notice Payload for a CALL operation — external call with optional ETH transfer
    struct Call {
        /// @notice The contract address to call
        address target;
        /// @notice ETH value (in wei) to forward with the call
        uint256 value;
        /// @notice ABI-encoded calldata to pass to the target
        bytes callargs;
    }

    /// @notice Payload for a LOG0 operation — emit a log with no indexed topics
    struct Log0 {
        /// @notice Unindexed log data
        bytes data;
    }

    /// @notice Payload for a LOG1 operation — emit a log with one indexed topic
    struct Log1 {
        /// @notice Unindexed log data
        bytes data;
        /// @notice First indexed topic
        bytes32 topic1;
    }

    /// @notice Payload for a LOG2 operation — emit a log with two indexed topics
    struct Log2 {
        /// @notice Unindexed log data
        bytes data;
        /// @notice First indexed topic
        bytes32 topic1;
        /// @notice Second indexed topic
        bytes32 topic2;
    }

    /// @notice Payload for a LOG3 operation — emit a log with three indexed topics
    struct Log3 {
        /// @notice Unindexed log data
        bytes data;
        /// @notice First indexed topic
        bytes32 topic1;
        /// @notice Second indexed topic
        bytes32 topic2;
        /// @notice Third indexed topic
        bytes32 topic3;
    }

    /// @notice Payload for a LOG4 operation — emit a log with four indexed topics
    struct Log4 {
        /// @notice Unindexed log data
        bytes data;
        /// @notice First indexed topic
        bytes32 topic1;
        /// @notice Second indexed topic
        bytes32 topic2;
        /// @notice Third indexed topic
        bytes32 topic3;
        /// @notice Fourth indexed topic
        bytes32 topic4;
    }
}
