// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {ConditionalTokens} from "../src/tokens/ConditionalTokens.sol";
import {DKIMRegistry} from "../src/zkemail/DKIMRegistry.sol";
import {DKIMVerifier} from "../src/zkemail/DKIMVerifier.sol";
import {HeadlineMarket} from "../src/market/HeadlineMarket.sol";
import {MarketFactory} from "../src/market/MarketFactory.sol";
import {FPMM} from "../src/market/FPMM.sol";

/// @notice Gnosis mainnet deployment (chain 100). Differences vs the local script:
/// no TestUSDC/faucet and no seeded markets (collateral = real Gnosis stablecoins:
/// WXDAI, USDC, USDC.e, sDAI, EURe — chosen per market in the app), and no Multicall3
/// (the canonical 0xcA11...CA11 is already deployed on Gnosis).
///
/// Registers real DKIM keys from deployments/dkim-keys.json: the demo dev key for the
/// sample fixtures plus the REAL nytimes.com key fetched from DNS, so a real NYT email
/// settles markets on mainnet.
///
///   forge script script/DeployGnosis.s.sol:DeployGnosis \
///     --rpc-url https://rpc.gnosischain.com --broadcast --private-key $PRIVATE_KEY
contract DeployGnosis is Script {
    function run() external {
        // Public deployments must explicitly name the fixed operator treasury.
        uint256 protocolFee = vm.envOr("PROTOCOL_FEE", uint256(22e15)); // 2.2%
        address feeRecipient = vm.envAddress("FEE_RECIPIENT");
        require(feeRecipient != address(0), "Deploy: missing fee recipient");
        vm.startBroadcast();

        ConditionalTokens ct = new ConditionalTokens();
        DKIMRegistry dkim = new DKIMRegistry();
        DKIMVerifier verifier = new DKIMVerifier(dkim);
        MarketFactory factory = new MarketFactory(
            ct, verifier, address(new HeadlineMarket()), address(new FPMM()), protocolFee, feeRecipient
        );

        registerKeysFromFile(dkim);

        vm.stopBroadcast();

        string memory json = "deployment";
        vm.serializeString(json, "protocolFee", vm.toString(factory.protocolFee()));
        vm.serializeAddress(json, "feeRecipient", factory.feeRecipient());
        vm.serializeAddress(json, "conditionalTokens", address(ct));
        vm.serializeAddress(json, "dkimRegistry", address(dkim));
        vm.serializeAddress(json, "verifier", address(verifier));
        // canonical Multicall3, predeployed on Gnosis
        vm.serializeAddress(json, "multicall3", 0xcA11bde05977b3631167028862bE2a173976CA11);
        // "usdc" = the app's default/faucet slot; on Gnosis point it at bridged USDC
        vm.serializeAddress(json, "usdc", 0xDDAfbb505ad214D7b80b1f830fcCc89B60fb7A83);
        vm.serializeUint(json, "chainId", block.chainid);
        string memory out = vm.serializeAddress(json, "factory", address(factory));
        vm.writeJson(out, "./deployments/gnosis.json");
    }

    function registerKeysFromFile(DKIMRegistry dkim) internal {
        string memory json = vm.readFile("./deployments/dkim-keys.json");
        uint256 n = vm.parseJsonUint(json, ".count");
        for (uint256 i = 0; i < n; i++) {
            string memory base = string.concat(".keys[", vm.toString(i), "]");
            dkim.registerKey(
                vm.parseJsonString(json, string.concat(base, ".domain")),
                vm.parseJsonString(json, string.concat(base, ".selector")),
                vm.parseJsonBytes(json, string.concat(base, ".exponent")),
                vm.parseJsonBytes(json, string.concat(base, ".modulus"))
            );
        }
    }
}
