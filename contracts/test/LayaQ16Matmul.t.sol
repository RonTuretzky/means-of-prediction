// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;
import {Test} from "forge-std/Test.sol";
import {LayaQ16Matmul} from "../src/judge/laya/LayaQ16Matmul.sol";

contract MatmulHarness {
    function run(int256[] memory x, uint256 width, bytes memory w, bytes memory s)
        external
        pure
        returns (int256[] memory)
    {
        return LayaQ16Matmul.run(x, width, w, s);
    }
}

contract LayaQ16MatmulTest is Test {
    MatmulHarness h;

    function setUp() public {
        h = new MatmulHarness();
    }

    function testSignedFloor() public {
        int256[] memory x = new int256[](2);
        x[0] = -3;
        x[1] = 3;
        int256[] memory y = h.run(x, 1, hex"0001", hex"00");
        assertEq(y[0], -1);
        assertEq(y[1], 0);
    }

    function testTiesEven() public {
        int256[] memory x = new int256[](6);
        x[0] = 65533;
        x[1] = 3;
        x[2] = -3;
        x[3] = 5;
        x[4] = -5;
        x[5] = -65533;
        int256[] memory y = h.run(x, 6, hex"000100010001000100010001", hex"0f");
        assertEq(y[0], 0);
    }

    function testRejectBadShape() public {
        int256[] memory x = new int256[](1);
        vm.expectRevert(LayaQ16Matmul.BadShape.selector);
        h.run(x, 2, hex"0001", hex"00");
    }

    function testRejectAsymmetricInt16() public {
        int256[] memory x = new int256[](1);
        vm.expectRevert(LayaQ16Matmul.BadMagnitude.selector);
        h.run(x, 1, hex"8000", hex"00");
    }

    function testRejectUnsafeWeightShift() public {
        int256[] memory x = new int256[](1);
        x[0] = 1;
        vm.expectRevert(LayaQ16Matmul.UnsafeShift.selector);
        h.run(x, 1, hex"0001", hex"11");
    }

    function testRejectUnsafeInputShift() public {
        int256[] memory x = new int256[](1);
        x[0] = int256(32767 << 17);
        vm.expectRevert(LayaQ16Matmul.UnsafeShift.selector);
        h.run(x, 1, hex"0001", hex"00");
    }

    function testRejectExtremeInput() public {
        int256[] memory x = new int256[](1);
        x[0] = type(int256).min;
        vm.expectRevert(LayaQ16Matmul.BadMagnitude.selector);
        h.run(x, 1, hex"0001", hex"00");
    }

    function testFuzzSmallExact(int16 a, int16 b, int16 c, int16 d) public {
        vm.assume(c != type(int16).min && d != type(int16).min);
        vm.assume(a != type(int16).min && b != type(int16).min);
        int256[] memory x = new int256[](2);
        x[0] = a;
        x[1] = b;
        int256[] memory y = h.run(x, 2, abi.encodePacked(c, d), hex"00");
        assertEq(y[0], (int256(a) * c + int256(b) * d) >> 16);
    }

    function _real(string memory name) private {
        string memory folder = vm.envOr("LAYA_QKV_FIXTURES", string(""));
        if (bytes(folder).length == 0) {
            vm.skip(true, "No real reference fixtures supplied");
            return;
        }
        bytes memory raw = vm.readFileBinary(string.concat(folder, "/", name, ".x.bin"));
        require(raw.length > 0 && raw.length % (32 * 1024) == 0, "Malformed embedding fixture");
        int256[] memory x = new int256[](raw.length / 32);
        for (uint256 i; i < x.length; ++i) {
            int256 v;
            assembly ("memory-safe") { v := mload(add(add(raw, 32), mul(i, 32))) }
            x[i] = v;
        }
        string memory meta = vm.readFile(string.concat(folder, "/", name, ".json"));
        bytes memory w = vm.readFileBinary(string.concat(folder, "/weights.bin"));
        bytes memory s = vm.readFileBinary(string.concat(folder, "/shifts.bin"));
        uint256 beforeGas = gasleft();
        int256[] memory y = h.run(x, 1024, w, s);
        uint256 used = beforeGas - gasleft();
        assertEq(y.length, vm.parseJsonUint(meta, ".scalars"));
        assertEq(sha256(abi.encodePacked(y)), vm.parseJsonBytes32(meta, ".expectedSHA256"));
        emit log_named_string("complete layer0 QKV case", name);
        emit log_named_uint("exact scalars", y.length);
        emit log_named_uint("kernel call gas", used);
    }

    function testReal_abc_0() public {
        _real("abc.q0");
    }

    function testReal_abc_1() public {
        _real("abc.q1");
    }

    function testReal_abc_2() public {
        _real("abc.q2");
    }

    function testReal_bbc_0() public {
        _real("bbc.q0");
    }

    function testReal_bbc_1() public {
        _real("bbc.q1");
    }

    function testReal_bbc_2() public {
        _real("bbc.q2");
    }

    function testReal_cnn_0() public {
        _real("cnn.q0");
    }

    function testReal_cnn_1() public {
        _real("cnn.q1");
    }

    function testReal_cnn_2() public {
        _real("cnn.q2");
    }

    function testReal_rfi_0() public {
        _real("rfi.q0");
    }

    function testReal_rfi_1() public {
        _real("rfi.q1");
    }

    function testReal_rfi_2() public {
        _real("rfi.q2");
    }
}
