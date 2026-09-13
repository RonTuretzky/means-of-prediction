// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @notice Verdict oracle consumed by judged markets. Verdicts are keyed by the keccak of the
/// exact prompt text (see JudgePrompt.userText), so the same headline judged for the same
/// market criteria resolves to one answer no matter who asked or which email carried it.
interface ILLMJudge {
    enum Verdict {
        None,
        Yes,
        No
    }

    function verdictOf(bytes32 promptKey) external view returns (Verdict);

    function promptKey(string calldata question, string calldata criteria, bytes calldata subject)
        external
        pure
        returns (bytes32);

    function userText(string calldata question, string calldata criteria, bytes calldata subject)
        external
        pure
        returns (bytes memory);
}
