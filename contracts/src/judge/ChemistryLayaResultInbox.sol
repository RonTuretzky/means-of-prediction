// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {GasKillerSDK} from "gas-killer-sdk/GasKillerSDK.sol";
import {
    IBLSSignatureChecker,
    IBLSSignatureCheckerTypes
} from "@eigenlayer-middleware/interfaces/IBLSSignatureChecker.sol";
import {BN254} from "@eigenlayer-middleware/libraries/BN254.sol";
import {LayaRequest} from "./LayaRequest.sol";

/// @dev Reject vacuous/zero-stake quorums before delegating to the configured real
/// checker. This is not an operator registry or a substitute signature checker.
contract ChemistryNonemptyQuorumChecker is IBLSSignatureChecker {
    IBLSSignatureChecker public immutable upstream;
    bytes32 public immutable expectedQuorumsHash;
    bytes32 public immutable upstreamCodeHash;
    error EmptyOrInvalidQuorum();

    constructor(IBLSSignatureChecker checker, bytes memory expectedQuorums) {
        if (address(checker).code.length == 0 || expectedQuorums.length == 0) revert EmptyOrInvalidQuorum();
        for (uint256 i = 1; i < expectedQuorums.length; ++i) {
            if (uint8(expectedQuorums[i]) <= uint8(expectedQuorums[i - 1])) revert EmptyOrInvalidQuorum();
        }
        upstream = checker;
        expectedQuorumsHash = keccak256(expectedQuorums);
        upstreamCodeHash = address(checker).codehash;
    }

    function checkSignatures(
        bytes32 hash,
        bytes calldata quorums,
        uint32 referenceBlock,
        NonSignerStakesAndSignature memory signature
    ) external view returns (QuorumStakeTotals memory totals, bytes32 signatoryRecord) {
        if (
            quorums.length == 0 || keccak256(quorums) != expectedQuorumsHash
                || address(upstream).codehash != upstreamCodeHash
        ) revert EmptyOrInvalidQuorum();
        (totals, signatoryRecord) = upstream.checkSignatures(hash, quorums, referenceBlock, signature);
        if (totals.totalStakeForQuorum.length != quorums.length || totals.signedStakeForQuorum.length != quorums.length)
        {
            revert EmptyOrInvalidQuorum();
        }
        for (uint256 i; i < quorums.length; ++i) {
            if (totals.totalStakeForQuorum[i] == 0 || totals.signedStakeForQuorum[i] > totals.totalStakeForQuorum[i]) {
                revert EmptyOrInvalidQuorum();
            }
        }
    }

    function trySignatureAndApkVerification(
        bytes32 hash,
        BN254.G1Point memory apk,
        BN254.G2Point memory apkG2,
        BN254.G1Point memory sigma
    ) external view returns (bool, bool) {
        return upstream.trySignatureAndApkVerification(hash, apk, apkG2, sigma);
    }
}

/// @notice GasKiller result transport boundary for the selected local Chemistry case.
/// @dev NOT a Laya executor. An actual operator execution integration must recompute
/// the complete pinned model before signing its CALL patch. A locally calculated
/// score or execution hash alone cannot populate this inbox. The SDK trusts its
/// quorum for arbitrary signed state patches; it does not prove inference here.
contract ChemistryLayaResultInbox is GasKillerSDK {
    bytes32 public constant DOMAIN_VERSION = keccak256("CHEMISTRY_LAYA_RESULT_INBOX_V1");
    address public immutable consumer;
    uint256 public immutable contextChainId;
    bytes32 public immutable contextModelPins;
    bytes32 public immutable contextRules;
    bytes32 public immutable contextSources;
    mapping(bytes32 => bool) public frozenRequests;
    mapping(bytes32 => LayaRequest.Result) private results;

    error NotCertifiedTransition();
    error WrongResultContext();
    error AlreadyRecorded();
    error MissingCertificate();
    event CertifiedResultRecorded(
        bytes32 indexed requestKey, bytes32 indexed executionRoot, uint32 aPpm, uint32 bPpm, uint256 transition
    );

    constructor(
        address avs,
        IBLSSignatureChecker checker,
        bytes memory expectedQuorums,
        address consumer_,
        LayaRequest.Request[] memory requests
    ) {
        if (avs == address(0) || consumer_ == address(0) || requests.length != 3) {
            revert WrongResultContext();
        }
        consumer = consumer_;
        contextChainId = block.chainid;
        contextModelPins = keccak256(abi.encode(requests[0].model));
        contextRules = requests[0].rulesHash;
        contextSources = requests[0].sourcePolicyHash;
        _setAvsAddress(avs);
        // AVS/checker/registry correspondence is deployment configuration and must
        // be verified independently. The SDK's namespace alone does not prove it.
        _setBlsSignatureChecker(address(new ChemistryNonemptyQuorumChecker(checker, expectedQuorums)));
        for (uint256 i; i < requests.length; ++i) {
            LayaRequest.validate(requests[i], block.timestamp, block.chainid, consumer_);
            if (
                keccak256(abi.encode(requests[i].model)) != contextModelPins || requests[i].rulesHash != contextRules
                    || requests[i].sourcePolicyHash != contextSources
            ) {
                revert WrongResultContext();
            }
            frozenRequests[LayaRequest.key(requests[i])] = true;
        }
    }

    function resultDomain() public view returns (bytes32) {
        return keccak256(abi.encode(DOMAIN_VERSION, contextChainId, address(this), consumer, uint256(5371179)));
    }

    /// @dev Expected as a self-CALL inside a real quorum-signed SDK transition.
    /// The consumer independently verifies the original complete signed email.
    function acceptCertifiedResult(
        bytes32 domain,
        LayaRequest.Request calldata request,
        LayaRequest.Result calldata result
    ) external {
        if (msg.sender != address(this) || !inTransition()) {
            revert NotCertifiedTransition();
        }
        if (domain != resultDomain() || block.chainid != contextChainId) revert WrongResultContext();
        LayaRequest.validate(request, block.timestamp, block.chainid, consumer);
        bytes32 key = LayaRequest.key(request);
        if (!frozenRequests[key]) revert WrongResultContext();
        LayaRequest.supportFlags(request, result); // checks key, score range and nonzero execution root
        if (results[key].version != 0) revert AlreadyRecorded();
        results[key] = result;
        emit CertifiedResultRecorded(key, result.executionRoot, result.aPpm, result.bPpm, stateTransitionCount());
    }

    function resultOf(bytes32 requestKey) external view returns (LayaRequest.Result memory result) {
        if (inTransition()) revert NotCertifiedTransition();
        result = results[requestKey];
        if (result.version == 0) revert MissingCertificate();
    }
}
