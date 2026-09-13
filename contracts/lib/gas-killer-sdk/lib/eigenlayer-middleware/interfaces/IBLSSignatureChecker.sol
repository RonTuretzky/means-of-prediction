// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.0;

import {BN254} from "../libraries/BN254.sol";

/// @notice MINIMAL mirror of eigenlayer-middleware `src/interfaces/IBLSSignatureChecker.sol`
/// (BreadchainCoop fork, commit fd26169c): the error/type interfaces verbatim and the one
/// function `GasKillerSDK` calls. Registry-coordinator getters are omitted (the SDK never
/// calls them); the settlement ABI is unchanged because it is fixed by the structs below.
interface IBLSSignatureCheckerErrors {
    error InvalidReferenceBlocknumber();
    error InputArrayLengthMismatch();
    error InputNonSignerLengthMismatch();
    error InvalidQuorumApkHash();
    error NonSignerPubkeysNotSorted();
    error StaleStakesForbidden();
    error InvalidBLSSignature();
}

interface IBLSSignatureCheckerTypes {
    struct NonSignerInfo {
        uint256[] quorumBitmaps;
        bytes32[] pubkeyHashes;
    }

    struct NonSignerStakesAndSignature {
        uint32[] nonSignerQuorumBitmapIndices;
        BN254.G1Point[] nonSignerPubkeys;
        BN254.G1Point[] quorumApks;
        BN254.G2Point apkG2;
        BN254.G1Point sigma;
        uint32[] quorumApkIndices;
        uint32[] totalStakeIndices;
        uint32[][] nonSignerStakeIndices;
    }

    struct QuorumStakeTotals {
        uint96[] signedStakeForQuorum;
        uint96[] totalStakeForQuorum;
    }
}

interface IBLSSignatureChecker is IBLSSignatureCheckerErrors, IBLSSignatureCheckerTypes {
    function checkSignatures(
        bytes32 msgHash,
        bytes calldata quorumNumbers,
        uint32 referenceBlockNumber,
        NonSignerStakesAndSignature memory nonSignerStakesAndSignature
    ) external view returns (QuorumStakeTotals memory, bytes32);

    function trySignatureAndApkVerification(
        bytes32 msgHash,
        BN254.G1Point memory apk,
        BN254.G2Point memory apkG2,
        BN254.G1Point memory sigma
    ) external view returns (bool pairingSuccessful, bool siganatureIsValid);
}
