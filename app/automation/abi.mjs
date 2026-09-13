import { parseAbi, getContractAddress } from 'viem';
export const proofStruct='struct EmailProof { string domainName; bytes32 publicKeyHash; uint256 timestamp; string fromAddress; string subject; string bodyExcerpt; bytes32 emailNullifier; bytes header; bytes signature; bytes canonicalBody; uint256 bodyOffset; uint256 bodyLength; }';
export const marketAbi=parseAbi([proofStruct,
 'struct Source { string name; string dkimDomain; string fromRegex; string contentRegex; }',
 'function question() view returns (string)', 'function getSources() view returns (Source[])',
 'function contentRegex() view returns (string)','function contentField() view returns (uint8)',
 'function criteria() view returns (string)','function windowStart() view returns (uint64)',
 'function deadline() view returns (uint64)','function resolution() view returns (uint8)',
 'function sourceMatched(uint256) view returns (bool)',
 'function checkProof(uint256 sourceIndex, EmailProof proof) view returns (bool ok,string reason)',
 'function submitProof(uint256 sourceIndex,EmailProof proof)',
]);
export const factoryAbi=parseAbi(['function marketCount() view returns (uint256)','function getMarket(uint256) view returns ((address market,address fpmm))','function verifier() view returns (address)','function marketImplementation() view returns (address)']);
export const bodyStoreAbi=parseAbi([proofStruct,'function chunkForHash(bytes32) view returns (address)','function storeChunk(bytes) returns (address)','function submitWithChunks(address market,uint256 sourceIndex,EmailProof proof,address[] pointers)']);
export const registryAbi=parseAbi(['function isDKIMPublicKeyHashValid(string domainName,bytes32 publicKeyHash) view returns (bool)']);
export const verifierAbi=parseAbi(['function bodyParsingVersion() view returns (uint256)']);
// This pinned factory creates exactly two EIP-1167 contracts per market, using CREATE.
// The signer can derive allowed market addresses without network access or trusting a caller's address list.
export const marketAddress=(factory,id)=>getContractAddress({from:factory,nonce:1n+2n*BigInt(id)});
