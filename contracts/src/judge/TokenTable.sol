// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title TokenTable
/// @notice Reader + canonical tokenizer over the Gas Killer engine-v3 raw-bytes token table
/// (the tokenizer blob every on-chain Qwen engine decodes answers with). Layout, exactly as
/// `tools/qwen3_convert.py build_tokenizer_blob` emits and `Qwen35Engine._decode` reads:
///
///   [u8 type=1][u32 vocab][u32 stringsLen][(vocab+1) x u32 offsets][strings]
///
/// The blob is not deployed: in overlay mode the operator mounts it as phantom code at
/// `overlayChunkAddress(manifest, weightChunks + i)` (24,575-byte chunks, `0x00 ||
/// payload`), which only exists inside the operators' simulation environment. So everything
/// here runs inside a tracked (Gas Killer-simulated) call, never in an ordinary transaction.
///
/// The canonical tokenizer is GREEDY LONGEST-MATCH over raw bytes (ties → lowest id). It is
/// a pure function of the bytes — the property a settlement needs: nobody gets to pick among
/// the exponentially many byte-equal segmentations of a headline. It is not HF byte-pair
/// merging; measured on our headline corpus the difference is a handful of rare-word splits.
library TokenTable {
    uint256 internal constant CHUNK = 24_575; // EIP-170 payload minus the 0x00 STOP prefix
    string internal constant OVERLAY_DOMAIN = "gaskiller.llm.overlay.v1";
    uint256 internal constant HEADER = 9; // u8 + u32 + u32

    error MalformedTokenTable();
    error TokenIdOutOfRange(uint256 id);
    error Untokenizable(uint256 at);

    /// @notice Overlay address of global chunk `i` of a manifest (mirrors Qwen35Engine).
    function overlayChunkAddress(bytes32 manifestHash, uint256 i) internal pure returns (address) {
        return address(uint160(uint256(keccak256(abi.encodePacked(OVERLAY_DOMAIN, manifestHash, uint64(i))))));
    }

    /// @notice Concatenate the tokenizer chunks `[first, first+n)` of `manifestHash` into one buffer
    /// of exactly `totalLen` bytes (each chunk's leading STOP byte skipped).
    function readOverlay(bytes32 manifestHash, uint256 first, uint256 n, uint256 totalLen)
        internal
        view
        returns (bytes memory table)
    {
        table = new bytes(totalLen);
        uint256 at = 0;
        for (uint256 i = 0; i < n; ++i) {
            address a = overlayChunkAddress(manifestHash, first + i);
            uint256 size = a.code.length;
            if (size < 2) revert MalformedTokenTable();
            uint256 len = size - 1;
            if (at + len > totalLen) revert MalformedTokenTable();
            assembly ("memory-safe") {
                extcodecopy(a, add(add(table, 0x20), at), 1, len)
            }
            at += len;
        }
        if (at != totalLen) revert MalformedTokenTable();
        if (uint8(table[0]) != 1) revert MalformedTokenTable();
    }

    function vocab(bytes memory table) internal pure returns (uint256) {
        if (table.length < HEADER) revert MalformedTokenTable();
        return _u32At(table, 1);
    }

    /// @notice Absolute (offset, length) of token `id`'s bytes inside `table`.
    function tokenSpan(bytes memory table, uint256 id) internal pure returns (uint256 off, uint256 len) {
        uint256 v = _u32At(table, 1);
        if (id >= v) revert TokenIdOutOfRange(id);
        uint256 stringsBase = HEADER + (v + 1) * 4;
        uint256 so = _u32At(table, HEADER + id * 4);
        uint256 eo = _u32At(table, HEADER + (id + 1) * 4);
        return (stringsBase + so, eo - so);
    }

    /// @notice Decode ids to raw bytes (no stop-token skipping: callers decide).
    function detokenize(bytes memory table, uint32[] memory ids) internal pure returns (bytes memory out) {
        uint256 total = 0;
        for (uint256 i = 0; i < ids.length; ++i) {
            (, uint256 len) = tokenSpan(table, ids[i]);
            total += len;
        }
        out = new bytes(total);
        uint256 w = 0;
        for (uint256 i = 0; i < ids.length; ++i) {
            (uint256 off, uint256 len) = tokenSpan(table, ids[i]);
            assembly ("memory-safe") {
                mcopy(add(add(out, 0x20), w), add(add(table, 0x20), off), len)
            }
            w += len;
        }
    }

    /// @notice Canonical greedy longest-match tokenization of `text` over ids `< idLimit`
    /// (so special/added tokens above the base vocab can never be produced). Ties → lowest id.
    /// Builds a first-byte bucket index once (packed uint32 ids, increasing within a bucket),
    /// then scans only the bucket of each position's first byte.
    function greedyTokenize(bytes memory table, bytes memory text, uint256 idLimit)
        internal
        pure
        returns (uint32[] memory ids)
    {
        uint256 v = _u32At(table, 1);
        if (idLimit > v) idLimit = v;
        uint256 stringsBase = HEADER + (v + 1) * 4;

        // --- first-byte bucket index over non-empty tokens below idLimit
        uint256[257] memory bucketStart; // bucketStart[b] = packed index of first id with first byte b
        {
            uint256[256] memory counts;
            for (uint256 id = 0; id < idLimit; ++id) {
                uint256 so = _u32At(table, HEADER + id * 4);
                uint256 eo = _u32At(table, HEADER + (id + 1) * 4);
                if (eo == so) continue;
                counts[uint8(table[stringsBase + so])]++;
            }
            uint256 acc = 0;
            for (uint256 b = 0; b < 256; ++b) {
                bucketStart[b] = acc;
                acc += counts[b];
            }
            bucketStart[256] = acc;
        }
        bytes memory packed = new bytes(bucketStart[256] * 4);
        {
            uint256[256] memory fill;
            for (uint256 id = 0; id < idLimit; ++id) {
                uint256 so = _u32At(table, HEADER + id * 4);
                uint256 eo = _u32At(table, HEADER + (id + 1) * 4);
                if (eo == so) continue;
                uint256 b = uint8(table[stringsBase + so]);
                uint256 slot = (bucketStart[b] + fill[b]) * 4;
                fill[b]++;
                assembly ("memory-safe") {
                    let p := add(add(packed, 0x20), slot)
                    mstore8(p, shr(24, id))
                    mstore8(add(p, 1), shr(16, id))
                    mstore8(add(p, 2), shr(8, id))
                    mstore8(add(p, 3), id)
                }
            }
        }

        // --- greedy scan
        uint32[] memory tmp = new uint32[](text.length); // upper bound: one id per byte
        uint256 n = 0;
        uint256 p = 0;
        while (p < text.length) {
            uint256 b = uint8(text[p]);
            (uint256 bestLen, uint256 bestId) =
                _bestMatch(table, stringsBase, packed, bucketStart[b], bucketStart[b + 1], text, p);
            if (bestLen == 0) revert Untokenizable(p);
            tmp[n++] = uint32(bestId);
            p += bestLen;
        }
        ids = new uint32[](n);
        for (uint256 i = 0; i < n; ++i) {
            ids[i] = tmp[i];
        }
    }

    /// @dev Longest token in packed bucket `[from, to)` that is a prefix of `text[p..]`;
    /// ties resolve to the lowest id because buckets are filled in increasing id order.
    function _bestMatch(
        bytes memory table,
        uint256 stringsBase,
        bytes memory packed,
        uint256 from,
        uint256 to,
        bytes memory text,
        uint256 p
    ) private pure returns (uint256 bestLen, uint256 bestId) {
        uint256 remaining = text.length - p;
        for (uint256 k = from; k < to; ++k) {
            uint256 id = _u32At(packed, k * 4);
            uint256 so = _u32At(table, HEADER + id * 4);
            uint256 len = _u32At(table, HEADER + (id + 1) * 4) - so;
            if (len <= bestLen || len > remaining) continue;
            if (_eq(table, stringsBase + so, text, p, len)) {
                bestLen = len;
                bestId = id;
            }
        }
    }

    /// @dev `a[ao..ao+len) == b[bo..bo+len)` (word-wise compare, tail masked).
    function _eq(bytes memory a, uint256 ao, bytes memory b, uint256 bo, uint256 len) private pure returns (bool same) {
        assembly ("memory-safe") {
            let pa := add(add(a, 0x20), ao)
            let pb := add(add(b, 0x20), bo)
            same := 1
            for { let i := 0 } lt(i, len) { i := add(i, 32) } {
                let rem := sub(len, i)
                let wa := mload(add(pa, i))
                let wb := mload(add(pb, i))
                if lt(rem, 32) {
                    let mask := not(sub(shl(mul(8, sub(32, rem)), 1), 1))
                    wa := and(wa, mask)
                    wb := and(wb, mask)
                }
                if iszero(eq(wa, wb)) {
                    same := 0
                    i := len
                }
            }
        }
    }

    function _u32At(bytes memory data, uint256 off) private pure returns (uint256 v) {
        assembly ("memory-safe") {
            v := shr(224, mload(add(add(data, 0x20), off)))
        }
    }
}
