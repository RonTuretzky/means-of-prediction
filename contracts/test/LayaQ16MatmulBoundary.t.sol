// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;
import {Test} from "forge-std/Test.sol";
import {LayaQ16Matmul} from "../src/judge/laya/LayaQ16Matmul.sol";

contract BoundaryHarness {
    function run(int256[] memory x, uint256 width, bytes memory w, bytes memory s)
        external
        pure
        returns (int256[] memory)
    {
        return LayaQ16Matmul.run(x, width, w, s);
    }
}

contract LayaQ16MatmulBoundaryTest is Test {
    BoundaryHarness h;

    function setUp() public {
        h = new BoundaryHarness();
    }

    function _tie(int256 v, int256 expected) private view {
        int256[] memory x = new int256[](2);
        x[0] = 65533;
        x[1] = v;
        int256[] memory y = h.run(x, 2, hex"00000001", hex"0f");
        assertEq(y[0], expected);
    }

    function testPositiveOddTie() public view {
        _tie(3, 2);
    }

    function testPositiveEvenTie() public view {
        _tie(5, 2);
    }

    function testNegativeOddTie() public view {
        _tie(-3, -2);
    }

    function testNegativeEvenTie() public view {
        _tie(-5, -2);
    }

    function testSmallPositiveTie() public view {
        _tie(1, 0);
    }

    function testSmallNegativeTie() public view {
        _tie(-1, 0);
    }

    function testDifferentInputRowShifts() public view {
        int256[] memory x = new int256[](4);
        x[0] = 1;
        x[1] = 3;
        x[2] = 65533;
        x[3] = 3;
        int256[] memory y = h.run(x, 2, hex"00000001", hex"0f");
        assertEq(y[0], 1);
        assertEq(y[1], 2);
    }

    function testDifferentWeightRowShifts() public view {
        int256[] memory x = new int256[](1);
        x[0] = 3;
        int256[] memory y = h.run(x, 1, hex"00010001", hex"0f10");
        assertEq(y[0], 1);
        assertEq(y[1], 3);
    }

    function testZeroRows() public view {
        int256[] memory x = new int256[](2);
        int256[] memory y = h.run(x, 2, hex"7fff8001", hex"10");
        assertEq(y[0], 0);
    }

    function testMaximumDot() public view {
        int256[] memory x = new int256[](4096);
        bytes memory w = new bytes(8192);
        for (uint256 i; i < 4096; ++i) {
            x[i] = 32767;
            w[2 * i] = 0x7f;
            w[2 * i + 1] = 0xff;
        }
        int256[] memory y = h.run(x, 4096, w, hex"10");
        assertEq(y[0], int256(uint256(4096) * 32767 * 32767));
    }

    function testRejectCombinedShift() public {
        int256[] memory x = new int256[](1);
        x[0] = 32768;
        vm.expectRevert(LayaQ16Matmul.UnsafeShift.selector);
        h.run(x, 1, hex"0001", hex"10");
    }

    function testWeightChangeChangesOutput() public view {
        int256[] memory x = new int256[](1);
        x[0] = 1234;
        int256[] memory a = h.run(x, 1, hex"0001", hex"10");
        int256[] memory b = h.run(x, 1, hex"0002", hex"10");
        assertTrue(a[0] != b[0]);
    }

    function testOddWidthCrossesPackedWordBoundary() public view {
        int256[] memory x = new int256[](3);
        x[0] = 2;
        x[1] = -3;
        x[2] = 5;
        bytes memory w = new bytes(42);
        bytes memory shifts = new bytes(7);
        for (uint256 j; j < 7; ++j) {
            shifts[j] = 0x10;
            for (uint256 k; k < 3; ++k) {
                int16 v = int16(int256(j * 3 + k) - 10);
                uint16 bits = uint16(v);
                w[2 * (j * 3 + k)] = bytes1(uint8(bits >> 8));
                w[2 * (j * 3 + k) + 1] = bytes1(uint8(bits));
            }
        }
        int256[] memory y = h.run(x, 3, w, shifts);
        for (uint256 j; j < 7; ++j) {
            assertEq(y[j], 2 * (int256(j * 3) - 10) - 3 * (int256(j * 3 + 1) - 10) + 5 * (int256(j * 3 + 2) - 10));
        }
    }

    function testRejectZeroWidth() public {
        int256[] memory x = new int256[](1);
        vm.expectRevert(LayaQ16Matmul.BadShape.selector);
        h.run(x, 0, hex"0001", hex"00");
    }

    function testRejectOverlargeWidth() public {
        int256[] memory x = new int256[](1);
        vm.expectRevert(LayaQ16Matmul.BadShape.selector);
        h.run(x, 4097, hex"0001", hex"00");
    }

    function testRejectTooManyRows() public {
        int256[] memory x = new int256[](321);
        vm.expectRevert(LayaQ16Matmul.BadShape.selector);
        h.run(x, 1, hex"0001", hex"00");
    }

    function testRejectZeroOutputs() public {
        int256[] memory x = new int256[](1);
        vm.expectRevert(LayaQ16Matmul.BadShape.selector);
        h.run(x, 1, hex"", hex"");
    }

    function testRejectMalformedWeightLength() public {
        int256[] memory x = new int256[](1);
        vm.expectRevert(LayaQ16Matmul.BadShape.selector);
        h.run(x, 1, hex"000100", hex"00");
    }
}
