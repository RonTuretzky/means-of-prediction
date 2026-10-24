// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {LayaLayerNorm} from "../src/judge/laya/LayaLayerNorm.sol";

contract LayaLayerNormHarness {
    function normalize(int256[] memory x, int256[] memory gamma) external pure returns (int256[] memory) {
        return LayaLayerNorm.normalize(x, gamma);
    }
}

contract LayaLayerNormTest is Test {
    LayaLayerNormHarness internal kernel;

    function setUp() public {
        kernel = new LayaLayerNormHarness();
    }

    function testSyntheticFiveFeatureDecimalReference() public {
        _checkDecimalReference(5, false);
    }

    function testSyntheticWidth128DecimalReferenceAndGas() public {
        _checkDecimalReference(128, true);
    }

    function testSyntheticWidth1024DecimalReferenceAndGas() public {
        _checkDecimalReference(1024, true);
    }

    /// @notice A private genuine encoder activation, supplied by the local reference exporter.
    /// @dev The fixture is never checked in. An absent env var is a reported Foundry skip,
    ///      not evidence of parity. Exact Q6 agreement only checks the integer replica;
    ///      floatOriginalQ6 separately exposes quantization/operator error.
    function testRealEncoderLayerNormFixture() public {
        string memory fixturePath = vm.envOr("LAYA_REAL_LAYERNORM_FIXTURE", string(""));
        if (bytes(fixturePath).length == 0) {
            vm.skip(true, "LAYA_REAL_LAYERNORM_FIXTURE absent; real activation test not run");
            return;
        }

        string[] memory command = new string[](2);
        command[0] = "cat";
        command[1] = fixturePath;
        string memory fixtureJson = string(vm.ffi(command));
        int256[] memory x = vm.parseJsonIntArray(fixtureJson, ".xQ6");
        int256[] memory gamma = vm.parseJsonIntArray(fixtureJson, ".gammaQ6");
        int256[] memory expected = vm.parseJsonIntArray(fixtureJson, ".expectedQ6");
        int256[] memory floatOriginal = vm.parseJsonIntArray(fixtureJson, ".floatOriginalQ6");
        assertEq(x.length, 1024, "real activation width");
        assertEq(gamma.length, 1024, "real gamma width");
        assertEq(expected.length, 1024, "integer reference width");
        assertEq(floatOriginal.length, 1024, "float reference width");

        uint256 gasBefore = gasleft();
        int256[] memory actual = kernel.normalize(x, gamma);
        uint256 usedGas = gasBefore - gasleft();
        uint256 maxFloatError;
        uint256 totalFloatError;
        for (uint256 i; i < 1024; ++i) {
            assertEq(actual[i], expected[i], "integer reference mismatch");
            uint256 error = _absoluteDifference(actual[i], floatOriginal[i]);
            if (error > maxFloatError) maxFloatError = error;
            totalFloatError += error;
        }
        emit log_named_uint("real activation width", 1024);
        emit log_named_uint("real activation max float32 error Q6", maxFloatError);
        emit log_named_uint("real activation mean float32 error Q6 x1000", totalFloatError * 1000 / 1024);
        emit log_named_uint("real activation LayerNorm external-call gas", usedGas);
    }

    function testConstantVectorHasZeroOutput() public view {
        int256[] memory x = new int256[](1024);
        int256[] memory gamma = new int256[](1024);
        for (uint256 i; i < x.length; ++i) {
            x[i] = -50_000_000;
            gamma[i] = 1_000_000;
        }
        int256[] memory result = kernel.normalize(x, gamma);
        for (uint256 i; i < result.length; ++i) {
            assertEq(result[i], 0);
        }
    }

    function testTinySpreadUsesEpsilonAndMeanCentering() public view {
        int256[] memory x = new int256[](2);
        int256[] memory gamma = new int256[](2);
        x[1] = 1; // Difference of one Q6 unit; epsilon dominates variance.
        gamma[0] = 1_000_000;
        gamma[1] = 1_000_000;
        int256[] memory result = kernel.normalize(x, gamma);
        assertEq(result[0], -158);
        assertEq(result[1], 158);
    }

    function testRangeBoundaryDoesNotOverflow() public view {
        int256[] memory x = new int256[](1024);
        int256[] memory gamma = new int256[](1024);
        for (uint256 i; i < x.length; ++i) {
            x[i] = i % 2 == 0 ? int256(1_000_000_000) : -int256(1_000_000_000);
            gamma[i] = i % 2 == 0 ? int256(1_000_000_000) : -int256(1_000_000_000);
        }
        int256[] memory result = kernel.normalize(x, gamma);
        assertEq(result.length, 1024);
        assertApproxEqAbs(result[0], 1_000_000_000, 1);
        assertApproxEqAbs(result[1], 1_000_000_000, 1);
    }

    function testRejectsEmptyMismatchedAndOutOfRangeInputs() public {
        int256[] memory empty = new int256[](0);
        vm.expectRevert(abi.encodeWithSelector(LayaLayerNorm.InvalidWidth.selector, 0));
        kernel.normalize(empty, empty);

        int256[] memory x = new int256[](1);
        vm.expectRevert(abi.encodeWithSelector(LayaLayerNorm.GammaWidthMismatch.selector, 1, 0));
        kernel.normalize(x, empty);

        int256[] memory gamma = new int256[](1);
        x[0] = 1_000_000_001;
        vm.expectRevert(abi.encodeWithSelector(LayaLayerNorm.InputOutOfRange.selector, 0));
        kernel.normalize(x, gamma);

        x[0] = 0;
        gamma[0] = -1_000_000_001;
        vm.expectRevert(abi.encodeWithSelector(LayaLayerNorm.GammaOutOfRange.selector, 0));
        kernel.normalize(x, gamma);

        x = new int256[](1025);
        gamma = new int256[](1025);
        vm.expectRevert(abi.encodeWithSelector(LayaLayerNorm.InvalidWidth.selector, 1025));
        kernel.normalize(x, gamma);
    }

    function _checkDecimalReference(uint256 width, bool measureGas) internal {
        string[] memory command = new string[](3);
        command[0] = "python3";
        command[1] = "../app/scripts/laya-demo/kernel_vectors.py";
        command[2] = vm.toString(width);
        string memory referenceJson = string(vm.ffi(command));
        int256[] memory x = vm.parseJsonIntArray(referenceJson, ".x");
        int256[] memory gamma = vm.parseJsonIntArray(referenceJson, ".gamma");
        int256[] memory expected = vm.parseJsonIntArray(referenceJson, ".expected");

        uint256 gasBefore = gasleft();
        int256[] memory actual = kernel.normalize(x, gamma);
        uint256 usedGas = gasBefore - gasleft();
        assertEq(actual.length, width);
        uint256 maxAbsoluteError;
        uint256 totalAbsoluteError;
        for (uint256 i; i < width; ++i) {
            uint256 error = _absoluteDifference(actual[i], expected[i]);
            if (error > maxAbsoluteError) maxAbsoluteError = error;
            totalAbsoluteError += error;
            assertLe(error, 2, "Q6 error exceeds two raw units");
        }
        emit log_named_uint("synthetic width", width);
        emit log_named_uint("max Q6 absolute error", maxAbsoluteError);
        emit log_named_uint("mean Q6 absolute error x1000", totalAbsoluteError * 1000 / width);
        if (measureGas) emit log_named_uint("LayerNorm external-call gas", usedGas);
    }

    function _absoluteDifference(int256 a, int256 b) internal pure returns (uint256) {
        return uint256(a >= b ? a - b : b - a);
    }
}
