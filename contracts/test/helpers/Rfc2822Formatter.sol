// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @notice Unix seconds -> an RFC 2822 `Date:` value, for building signed test fixtures.
///
/// This is a standalone contract rather than a library so that call sites cross a real
/// call boundary: inlined into MarketTestBase.makeProofWithBody the string building blows
/// the Yul stack, even with via_ir. Test-only; never deployed to a real network.
contract Rfc2822Formatter {
    /// @return e.g. "Wed, 12 Aug 2026 18:03:11 +0000" (always UTC).
    function format(uint256 ts) external pure returns (string memory) {
        uint256 dayCount = ts / 86400;
        uint256 rem = ts % 86400;

        // civil_from_days (Howard Hinnant), era-based
        uint256 z = dayCount + 719468;
        uint256 era = z / 146097;
        uint256 doe = z - era * 146097;
        uint256 yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
        uint256 y = yoe + era * 400;
        uint256 doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
        uint256 mp = (5 * doy + 2) / 153;
        uint256 d = doy - (153 * mp + 2) / 5 + 1;
        uint256 m = mp < 10 ? mp + 3 : mp - 9;
        if (m <= 2) y += 1;

        // 1970-01-01 was a Thursday
        string[7] memory wdays = ["Thu", "Fri", "Sat", "Sun", "Mon", "Tue", "Wed"];
        string[13] memory months =
            ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

        return string.concat(
            wdays[dayCount % 7],
            ", ",
            pad2(d),
            " ",
            months[m],
            " ",
            uintToString(y),
            " ",
            pad2(rem / 3600),
            ":",
            pad2((rem % 3600) / 60),
            ":",
            pad2(rem % 60),
            " +0000"
        );
    }

    function pad2(uint256 v) private pure returns (string memory) {
        return v < 10 ? string.concat("0", uintToString(v)) : uintToString(v);
    }

    function uintToString(uint256 v) private pure returns (string memory) {
        if (v == 0) return "0";
        uint256 len;
        for (uint256 t = v; t != 0; t /= 10) len++;
        bytes memory buf = new bytes(len);
        while (v != 0) {
            buf[--len] = bytes1(uint8(48 + (v % 10)));
            v /= 10;
        }
        return string(buf);
    }
}
