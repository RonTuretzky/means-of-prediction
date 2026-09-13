// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;
import {MarketTestBase} from "./MarketTestBase.sol";

contract DKIMRegistryTest is MarketTestBase {
    function test_AttackerCannotRegisterKeyForNewspaper() public {
        vm.prank(bob);
        vm.expectRevert("DKIM: not registrar");
        dkim.registerKey("nytimes.com", "attacker", devExponent, devModulus);
    }
    function test_OnlyRegistrarCanRevoke() public {
        vm.prank(bob);
        vm.expectRevert("DKIM: not registrar");
        dkim.revokeKey("nytimes.com", devKeyHash);
        dkim.revokeKey("nytimes.com", devKeyHash);
        assertFalse(dkim.isDKIMPublicKeyHashValid("nytimes.com", devKeyHash));
    }
    function test_RevokedModulusCannotBeReauthorized() public {
        dkim.revokeKey("nytimes.com", devKeyHash);
        vm.expectRevert("DKIM: key already registered");
        dkim.registerKey("nytimes.com", "another-selector", devExponent, devModulus);
    }
}
