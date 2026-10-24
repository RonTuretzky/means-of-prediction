// SPDX-License-Identifier: AGPL-3.0-only
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {LayaMatmul} from "../src/judge/laya/LayaMatmul.sol";

contract LayaMatmulHarness {
    function run(bytes memory packed, uint256 rows, uint256 cols, uint256 weightBytes, int256[] memory x)
        external
        pure
        returns (int256[] memory)
    {
        return LayaMatmul.matmulRows(packed, rows, cols, weightBytes, x);
    }
}

contract LayaMatmulTest is Test {
    LayaMatmulHarness internal kernel;

    function setUp() public {
        kernel = new LayaMatmulHarness();
    }

    function testNegativeArithmeticShiftFloors() public view {
        int256[] memory x = new int256[](1024);
        x[0] = 1;
        bytes memory packed = new bytes(1025);
        packed[0] = 0x01; // row shift 1
        packed[1] = 0xff; // signed int8 -1
        int256[] memory out = kernel.run(packed, 1, 1024, 1, x);
        assertEq(out[0], -1); // -1 >> 1 floors, whereas division toward zero would give 0.
    }

    function testRejectsInvalidShapeAndBounds() public {
        int256[] memory x = new int256[](1024);
        bytes memory packed = new bytes(1025);
        vm.expectRevert(abi.encodeWithSelector(LayaMatmul.InvalidShape.selector, 0, 1024));
        kernel.run(packed, 0, 1024, 1, x);
        vm.expectRevert(abi.encodeWithSelector(LayaMatmul.InvalidShape.selector, 33, 1024));
        kernel.run(packed, 33, 1024, 1, x);
        vm.expectRevert(abi.encodeWithSelector(LayaMatmul.InvalidShape.selector, 1, 1023));
        kernel.run(packed, 1, 1023, 1, x);
        vm.expectRevert(abi.encodeWithSelector(LayaMatmul.InvalidWeightBytes.selector, 3));
        kernel.run(packed, 1, 1024, 3, x);
        vm.expectRevert(abi.encodeWithSelector(LayaMatmul.PackedLengthMismatch.selector, 0, 1025));
        kernel.run(new bytes(0), 1, 1024, 1, x);
        vm.expectRevert(abi.encodeWithSelector(LayaMatmul.InputWidthMismatch.selector, 0));
        kernel.run(packed, 1, 1024, 1, new int256[](0));
        x[0] = (int256(1) << 31) + 1;
        vm.expectRevert(abi.encodeWithSelector(LayaMatmul.InputOutOfRange.selector, 0));
        kernel.run(packed, 1, 1024, 1, x);
        x[0] = 0;
        packed[0] = 0x20;
        vm.expectRevert(abi.encodeWithSelector(LayaMatmul.ShiftOutOfRange.selector, 0));
        kernel.run(packed, 1, 1024, 1, x);
    }

    /// @dev A private fixture of actual checkpoint weights and an approximately Q24-converted
    ///      genuine LayerNorm output. Missing env is an explicit skip, never a parity claim.
    function testActualWeight32x1024I8AndI16() public {
        string memory fixturePath = vm.envOr("LAYA_REAL_MATMUL_FIXTURE", string(""));
        if (bytes(fixturePath).length == 0) {
            vm.skip(true, "LAYA_REAL_MATMUL_FIXTURE absent; actual-weight matmul test not run");
            return;
        }
        string[] memory command = new string[](2);
        command[0] = "cat";
        command[1] = fixturePath;
        string memory fixture = string(vm.ffi(command));
        int256[] memory x = vm.parseJsonIntArray(fixture, ".xQ24");
        bytes memory packedI8 = vm.parseJsonBytes(fixture, ".packedI8");
        bytes memory packedI16 = vm.parseJsonBytes(fixture, ".packedI16");
        int256[] memory expectedI8 = vm.parseJsonIntArray(fixture, ".expectedI8Q24");
        int256[] memory expectedI16 = vm.parseJsonIntArray(fixture, ".expectedI16Q24");
        int256[] memory floatReference = vm.parseJsonIntArray(fixture, ".floatReferenceQ24");
        assertEq(x.length, 1024);
        assertEq(expectedI8.length, 32);
        assertEq(expectedI16.length, 32);
        assertEq(floatReference.length, 32);

        uint256 gasBefore = gasleft();
        int256[] memory actualI8 = kernel.run(packedI8, 32, 1024, 1, x);
        uint256 gasI8 = gasBefore - gasleft();
        gasBefore = gasleft();
        int256[] memory actualI16 = kernel.run(packedI16, 32, 1024, 2, x);
        uint256 gasI16 = gasBefore - gasleft();

        uint256 maxDriftI8;
        uint256 maxDriftI16;
        uint256 sumDriftI8;
        uint256 sumDriftI16;
        for (uint256 i; i < 32; ++i) {
            assertEq(actualI8[i], expectedI8[i], "int8 integer reference mismatch");
            assertEq(actualI16[i], expectedI16[i], "int16 integer reference mismatch");
            uint256 driftI8 = _absoluteDifference(actualI8[i], floatReference[i]);
            uint256 driftI16 = _absoluteDifference(actualI16[i], floatReference[i]);
            if (driftI8 > maxDriftI8) maxDriftI8 = driftI8;
            if (driftI16 > maxDriftI16) maxDriftI16 = driftI16;
            sumDriftI8 += driftI8;
            sumDriftI16 += driftI16;
        }
        emit log_named_uint("actual-weight projection rows", 32);
        emit log_named_uint("projection MACs per call", 32 * 1024);
        emit log_named_uint("int8 external-call gas", gasI8);
        emit log_named_uint("int16 external-call gas", gasI16);
        emit log_named_uint("int8 max Q24 drift vs Q6-input float", maxDriftI8);
        emit log_named_uint("int16 max Q24 drift vs Q6-input float", maxDriftI16);
        emit log_named_uint("int8 mean Q24 drift", sumDriftI8 / 32);
        emit log_named_uint("int16 mean Q24 drift", sumDriftI16 / 32);
    }

    function _absoluteDifference(int256 a, int256 b) private pure returns (uint256) {
        return uint256(a >= b ? a - b : b - a);
    }
}
