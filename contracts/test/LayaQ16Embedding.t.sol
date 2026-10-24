// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {LayaQ16LayerNorm} from "../src/judge/laya/LayaQ16LayerNorm.sol";
import {LayaQ16Embedding} from "../src/judge/laya/LayaQ16Embedding.sol";

contract LayaQ16EmbeddingHarness {
    function run(uint32[] memory ids, uint32[] memory table, bytes memory rows, bytes memory gamma)
        external
        pure
        returns (int256[] memory)
    {
        return LayaQ16Embedding.run(ids, table, rows, gamma);
    }

    function norm(int256[] memory x, int256[] memory gamma, int256[] memory bias)
        external
        pure
        returns (int256[] memory)
    {
        return LayaQ16LayerNorm.normalize(x, gamma, bias);
    }
}

contract LayaQ16EmbeddingTest is Test {
    LayaQ16EmbeddingHarness private kernel;

    function setUp() public {
        kernel = new LayaQ16EmbeddingHarness();
    }

    function _read(string memory path) private returns (string memory) {
        string[] memory cmd = new string[](2);
        cmd[0] = "cat";
        cmd[1] = path;
        return string(vm.ffi(cmd));
    }

    function _ids(string memory data, string memory key) private pure returns (uint32[] memory out) {
        uint256[] memory raw = vm.parseJsonUintArray(data, key);
        out = new uint32[](raw.length);
        for (uint256 i; i < raw.length; ++i) {
            require(raw[i] < 50368);
            out[i] = uint32(raw[i]);
        }
    }

    function _fixture(string memory name) private returns (string memory weights, string memory item) {
        string memory folder = vm.envOr("LAYA_Q16_EMBEDDING_FIXTURES", string(""));
        if (bytes(folder).length == 0) {
            vm.skip(true, "Private pinned embedding fixtures absent; no real parity claim");
            return ("", "");
        }
        weights = _read(string.concat(folder, "/weights.private.json"));
        item = _read(string.concat(folder, "/", name, ".private.json"));
        assertEq(
            vm.parseJsonBytes32(weights, ".modelSHA256"),
            0x5ed8ce354cb1bf9f313fb4791f74601acbf955598d74f8d6742da3497aee5169
        );
        assertEq(
            vm.parseJsonBytes32(weights, ".runtimeSHA256"),
            0xb06bce0d8250d8d3d6345278662feea160429cdf746ef26a5af1000489c54766
        );
        assertEq(
            vm.parseJsonBytes32(weights, ".exportSHA256"),
            0xb863c72eb531b7f86c67f23cf233067665e18b98f87a978eb2f6a4417e78b51d
        );
    }

    function _real(string memory name) private {
        (string memory weights, string memory item) = _fixture(name);
        uint32[] memory ids = _ids(item, ".tokenIds");
        uint32[] memory table = _ids(weights, ".tableIds");
        bytes memory rows = vm.parseJsonBytes(weights, ".packedRows");
        bytes memory gamma = vm.parseJsonBytes(weights, ".packedGamma");
        assertEq(sha256(rows), vm.parseJsonBytes32(weights, ".rowsSHA256"));
        assertEq(sha256(gamma), vm.parseJsonBytes32(weights, ".gammaSHA256"));
        uint256 beforeGas = gasleft();
        int256[] memory actual = kernel.run(ids, table, rows, gamma);
        uint256 callGas = beforeGas - gasleft();
        assertEq(actual.length, vm.parseJsonUint(item, ".expectedScalarCount"));
        assertEq(sha256(abi.encodePacked(actual)), vm.parseJsonBytes32(item, ".expectedSHA256"), name);
        emit log_named_string("complete embedding case", name);
        emit log_named_uint("exact Q16 scalar count", actual.length);
        emit log_named_uint("embedding kernel external-call gas only", callGas);
    }

    function testRealBBCq() public {
        _real("bbc.q0");
    }

    function testRealBBCA() public {
        _real("bbc.q1");
    }

    function testRealBBCB() public {
        _real("bbc.q2");
    }

    function testRealCNNq() public {
        _real("cnn.q0");
    }

    function testRealCNNA() public {
        _real("cnn.q1");
    }

    function testRealCNNB() public {
        _real("cnn.q2");
    }

    function testRealABCq() public {
        _real("abc.q0");
    }

    function testRealABCA() public {
        _real("abc.q1");
    }

    function testRealABCB() public {
        _real("abc.q2");
    }

    function testRealRFIq() public {
        _real("rfi.q0");
    }

    function testRealRFIA() public {
        _real("rfi.q1");
    }

    function testRealRFIB() public {
        _real("rfi.q2");
    }

    function testRealWeightAndTokenMutationsChangeComputedResult() public {
        (string memory weights, string memory item) = _fixture("bbc.q0");
        uint32[] memory allIds = _ids(item, ".tokenIds");
        uint32[] memory ids = new uint32[](2);
        ids[0] = allIds[0];
        ids[1] = allIds[1];
        uint32[] memory table = _ids(weights, ".tableIds");
        bytes memory rows = vm.parseJsonBytes(weights, ".packedRows");
        bytes memory gamma = vm.parseJsonBytes(weights, ".packedGamma");
        bytes32 expected = vm.parseJsonBytes32(item, ".firstTwoExpectedSHA256");
        assertEq(sha256(abi.encodePacked(kernel.run(ids, table, rows, gamma))), expected);
        (ids[0], ids[1]) = (ids[1], ids[0]);
        assertNotEq(sha256(abi.encodePacked(kernel.run(ids, table, rows, gamma))), expected);
        (ids[0], ids[1]) = (ids[1], ids[0]);
        uint256 index;
        while (table[index] != ids[0]) ++index;
        // Change a real embedding coefficient's magnitude, leaving shape/transport valid.
        rows[index * 4096 + 1] = bytes1(uint8(rows[index * 4096 + 1]) ^ 0x01);
        assertNotEq(sha256(abi.encodePacked(kernel.run(ids, table, rows, gamma))), expected);
    }

    function testSignedMeanFloorNormalizationTruncationAndGammaFloor() public view {
        int256[] memory x = new int256[](1024);
        x[0] = -1;
        int256[] memory gamma = new int256[](1024);
        for (uint256 i; i < 1024; ++i) {
            gamma[i] = 65536;
        }
        gamma[2] = -1;
        int256[] memory out = kernel.norm(x, gamma, new int256[](0));
        // mean=-1, variance=0, floor sqrt(42950)=207; trunc(65536/207)=316.
        assertEq(out[0], 0);
        assertEq(out[1], 316);
        assertEq(out[2], -1);
    }

    function testConstantRowsAndOptionalBias() public view {
        int256[] memory x = new int256[](2048);
        int256[] memory gamma = new int256[](1024);
        int256[] memory bias = new int256[](1024);
        for (uint256 i; i < 1024; ++i) {
            x[i] = -17;
            x[1024 + i] = 31;
            gamma[i] = 65536;
            bias[i] = int256(i) - 512;
        }
        int256[] memory out = kernel.norm(x, gamma, bias);
        for (uint256 i; i < 2048; ++i) {
            assertEq(out[i], bias[i % 1024]);
        }
    }

    function testMagnitudeAndVarianceSumGuards() public {
        int256[] memory x = new int256[](1024);
        int256[] memory gamma = new int256[](1024);
        x[0] = int256(1 << 52);
        vm.expectRevert(LayaQ16LayerNorm.MagnitudeOverflow.selector);
        kernel.norm(x, gamma, new int256[](0));
        for (uint256 i; i < 1024; ++i) {
            x[i] = i % 2 == 0 ? int256(1 << 26) : -int256(1 << 26);
        }
        vm.expectRevert(LayaQ16LayerNorm.MagnitudeOverflow.selector);
        kernel.norm(x, gamma, new int256[](0));
    }

    function testRejectsMalformedAndMissingWeightRows() public {
        uint32[] memory ids = new uint32[](2);
        ids[0] = 1;
        ids[1] = 2;
        uint32[] memory table = new uint32[](2);
        table[0] = 1;
        table[1] = 2;
        bytes memory rows = new bytes(8192);
        bytes memory gamma = new bytes(4096);
        vm.expectRevert(LayaQ16Embedding.BadTable.selector);
        kernel.run(ids, table, new bytes(8191), gamma);
        table[1] = 1;
        vm.expectRevert(LayaQ16Embedding.BadTable.selector);
        kernel.run(ids, table, rows, gamma);
        table[1] = 3;
        vm.expectRevert(abi.encodeWithSelector(LayaQ16Embedding.MissingToken.selector, 2));
        kernel.run(ids, table, rows, gamma);
        ids[1] = 50368;
        vm.expectRevert(LayaQ16Embedding.BadTokens.selector);
        kernel.run(ids, table, rows, gamma);
        vm.expectRevert(LayaQ16LayerNorm.BadShape.selector);
        kernel.norm(new int256[](1023), new int256[](1024), new int256[](0));
    }
}
