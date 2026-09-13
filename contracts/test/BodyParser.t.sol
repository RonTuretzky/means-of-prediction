// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;
import {MarketTestBase} from "./MarketTestBase.sol";
import {EmailProof} from "../src/dkim/IDKIMVerifier.sol";
import {BodyParser} from "../src/lib/BodyParser.sol";
import {HeadlineMarket} from "../src/market/HeadlineMarket.sol";
import {MarketFactory} from "../src/market/MarketFactory.sol";
contract BodyParserTest is MarketTestBase {
    function proofFor(bytes memory body, string memory ct, string memory cte, string memory extra) internal returns (EmailProof memory p) {
        p = makeProof("nytimes.com", block.timestamp, "nytdirect@nytimes.com", "Daily newsletter", "", bytes32(0));
        p.header = bytes.concat(signedHeader(p.fromAddress, p.subject, p.timestamp, 0), bytes(string.concat("\r\ncontent-type:", ct, cte,
            "\r\ndkim-signature:v=1; a=rsa-sha256; c=relaxed/relaxed; d=nytimes.com; s=dev2026; bh=",
            vm.toBase64(abi.encodePacked(sha256(body))), extra, "; h=from:subject:date:content-type; b=")));
        p.signature = rsaSign(p.header); p.emailNullifier = keccak256(p.signature); p.canonicalBody = body; p.bodyLength = body.length;
    }
    function htmlProof() internal returns (EmailProof memory p) {
        p = proofFor("<p>Helena Foulkes won the Demo=\r\ncratic primary.</p>\r\n", "text/html; charset=utf-8", "", "");
        p.bodyExcerpt = "<p>Helena Foulkes won the Democratic primary.</p>\r\n";
    }
    function test_RealRsaHtmlBodySettlesAndPaysOut() public {
        EmailProof memory p = htmlProof(); assertTrue(verifier.verify(p));
        MarketFactory.CreateMarketParams memory cfg = defaultParams(); cfg.contentField = HeadlineMarket.ContentField.Body;
        cfg.contentRegex = "Helena Foulkes won the Democratic primary"; cfg.threshold = 1;
        (HeadlineMarket m,) = factory.createMarket(cfg);
        (bool ok,) = m.checkProof(0, p); assertTrue(ok); m.submitProof(0, p);
        assertEq(uint256(m.resolution()), 1); assertEq(ct.payoutNumerators(m.conditionId(), 0), 1); assertEq(ct.payoutNumerators(m.conditionId(), 1), 0);
        vm.expectRevert("Market: already resolved"); m.submitProof(0, p);
    }
    function test_TamperedBodyRejected() public { EmailProof memory p = htmlProof(); p.canonicalBody[4] = "X"; assertFalse(verifier.verify(p)); }
    function test_ForgedExcerptRejected() public { EmailProof memory p = htmlProof(); p.bodyExcerpt = "The Fed cuts rates"; assertFalse(verifier.verify(p)); }
    function test_UnsignedAppendRejected() public { EmailProof memory p = htmlProof(); p.canonicalBody = bytes.concat(p.canonicalBody, "forged report"); assertFalse(verifier.verify(p)); }
    function test_PartialBodyHashRejected() public {
        EmailProof memory p = proofFor("hello\r\n", "text/plain", "", "; l=7"); p.bodyExcerpt = "hello\r\n"; assertFalse(verifier.verify(p));
        p = proofFor("hello\r\n", "text/plain", "", "; l=7; l=7"); p.bodyExcerpt = "hello\r\n"; assertFalse(verifier.verify(p));
    }
    function test_DuplicateBodyHashRejected() public {
        EmailProof memory p = proofFor("hello\r\n", "text/plain", "", "; bh=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="); p.bodyExcerpt = "hello\r\n"; assertFalse(verifier.verify(p));
    }
    function test_UnsupportedMimeAndEncodingRejected() public {
        EmailProof memory p = proofFor("hello\r\n", "multipart/alternative; boundary=test", "", ""); p.bodyExcerpt = "hello\r\n"; assertFalse(verifier.verify(p));
        p = proofFor("hello\r\n", "text/plain", "\r\ncontent-transfer-encoding:base64", ""); p.bodyExcerpt = "hello\r\n"; assertFalse(verifier.verify(p));
    }
    function test_SignedIdentityPreservesEquals() public {
        EmailProof memory p = proofFor("a=20b\r\n", "text/plain", "\r\ncontent-transfer-encoding:7bit", ""); p.bodyExcerpt = "a=20b\r\n"; assertTrue(verifier.verify(p));
        p.bodyExcerpt = "a b\r\n"; assertFalse(verifier.verify(p));
    }
    function test_CroppedAnchorCannotMatchAsWholeBody() public {
        EmailProof memory p = proofFor("Correction: The Fed cuts rates was a false alert.\r\n", "text/plain", "", "");
        p.bodyOffset = 12; p.bodyLength = 18; p.bodyExcerpt = "The Fed cuts rates"; assertTrue(verifier.verify(p));
        MarketFactory.CreateMarketParams memory cfg = defaultParams(); cfg.contentField = HeadlineMarket.ContentField.Body;
        cfg.contentRegex = "^The Fed cuts rates$"; cfg.threshold = 1;
        vm.expectRevert("Market: body anchors unsupported"); factory.createMarket(cfg);
    }
    function test_OffsetsAndBrokenEscapesRejected() public {
        EmailProof memory p = htmlProof(); p.bodyOffset = type(uint256).max; assertFalse(verifier.verify(p));
        p = htmlProof(); p.bodyLength = 4097; assertFalse(verifier.verify(p));
        p = proofFor("a=20b\r\n", "text/plain", "", ""); p.bodyOffset = 2; p.bodyLength = 1; p.bodyExcerpt = "2"; assertFalse(verifier.verify(p));
        p.bodyOffset = 0; p.bodyLength = 2; p.bodyExcerpt = "a="; assertFalse(verifier.verify(p));
    }
    function test_ChangingSigningDomainWithSharedKeyRejected() public { EmailProof memory p = htmlProof(); p.domainName = "email.reuters.com"; assertFalse(verifier.verify(p)); }
    function testFuzz_Base64Roundtrip(bytes32 hash) public pure {
        (bytes32 decoded, bool ok) = BodyParser.bodyHash(bytes(vm.toBase64(abi.encodePacked(hash)))); assertTrue(ok); assertEq(decoded, hash);
    }
    function test_PatternAnchorsAndLiteralCurrency() public pure {
        assertFalse(BodyParser.substringPattern("a$|^b")); assertTrue(BodyParser.substringPattern("[^a].*\\$40"));
    }
}
