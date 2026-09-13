// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {IDKIMRegistry} from "./IDKIMVerifier.sol";

/// @title DKIMRegistry
/// @notice Stores REAL DKIM public keys (RSA modulus + exponent) per signing domain,
/// as published in the domain's DNS (`<selector>._domainkey.<domain>` TXT record).
/// The deploying registrar authenticates DNS keys before registering them. Without
/// this authority (or an onchain DNSSEC proof), accepting arbitrary key/domain pairs
/// would let anyone impersonate a newspaper using their own RSA private key.
/// Revocation is permanent for a modulus; historical validity windows remain future work.
contract DKIMRegistry is IDKIMRegistry {
    address public immutable registrar;

    constructor() { registrar = msg.sender; }

    modifier onlyRegistrar() {
        require(msg.sender == registrar, "DKIM: not registrar");
        _;
    }
    event DKIMKeyRegistered(string domainName, bytes32 indexed publicKeyHash, string selector);
    event DKIMKeyRevoked(string domainName, bytes32 indexed publicKeyHash);

    struct Key {
        bytes modulus;
        bytes exponent;
        address registrant;
        bool valid;
    }

    // keccak(domain) => keccak(modulus) => key
    mapping(bytes32 => mapping(bytes32 => Key)) private _keys;

    function isDKIMPublicKeyHashValid(string calldata domainName, bytes32 publicKeyHash)
        external
        view
        returns (bool)
    {
        return _keys[keccak256(bytes(domainName))][publicKeyHash].valid;
    }

    /// @notice Register a real DKIM public key for a domain.
    /// @param exponent big-endian public exponent (e.g. hex"010001" for 65537)
    /// @param modulus big-endian RSA modulus (the DNS `p=` key)
    function registerKey(string calldata domainName, string calldata selector, bytes calldata exponent, bytes calldata modulus)
        external
        onlyRegistrar
        returns (bytes32 publicKeyHash)
    {
        require(modulus.length >= 128, "DKIM: modulus too short"); // >= 1024-bit
        require(exponent.length > 0 && exponent.length <= 8, "DKIM: bad exponent");
        publicKeyHash = keccak256(modulus);
        Key storage k = _keys[keccak256(bytes(domainName))][publicKeyHash];
        require(k.registrant == address(0), "DKIM: key already registered");
        k.modulus = modulus;
        k.exponent = exponent;
        k.registrant = msg.sender;
        k.valid = true;
        emit DKIMKeyRegistered(domainName, publicKeyHash, selector);
    }

    /// @notice The registrant may revoke a key (e.g. after DNS rotation).
    function revokeKey(string calldata domainName, bytes32 publicKeyHash) external onlyRegistrar {
        Key storage k = _keys[keccak256(bytes(domainName))][publicKeyHash];
        require(k.registrant == msg.sender, "DKIM: not registrant");
        k.valid = false;
        emit DKIMKeyRevoked(domainName, publicKeyHash);
    }

    function keyData(string calldata domainName, bytes32 publicKeyHash)
        external
        view
        returns (bytes memory modulus, bytes memory exponent, bool valid)
    {
        Key storage k = _keys[keccak256(bytes(domainName))][publicKeyHash];
        return (k.modulus, k.exponent, k.valid);
    }
}
