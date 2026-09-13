// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;
import {MarketTestBase} from "./MarketTestBase.sol";
import {EmailBodyStore} from "../src/dkim/EmailBodyStore.sol";
import {EmailProof} from "../src/dkim/IDKIMVerifier.sol";
import {HeadlineMarket} from "../src/market/HeadlineMarket.sol";
import {MarketFactory} from "../src/market/MarketFactory.sol";
contract EmailBodyStoreTest is MarketTestBase {
    EmailBodyStore store;
    function setUp() public override {super.setUp();store = new EmailBodyStore();}
    function proof() internal returns (EmailProof memory p, address[] memory chunks, HeadlineMarket market) {
        bytes memory body = "<p>Foulkes won the Demo=\r\ncratic primary.</p>\r\n";
        p = makeProof("nytimes.com",block.timestamp,"nytdirect@nytimes.com","Daily newsletter","",0);
        p.header = bytes.concat(signedHeader(p.fromAddress,p.subject,p.timestamp,0),bytes(string.concat(
            "\r\ncontent-type:text/html; charset=utf-8\r\ndkim-signature:v=1; a=rsa-sha256; c=relaxed/relaxed; d=nytimes.com; s=dev2026; bh=",vm.toBase64(abi.encodePacked(sha256(body))),"; b=")));
        p.signature=rsaSign(p.header);p.emailNullifier=keccak256(p.signature);
        p.bodyLength=body.length;p.bodyExcerpt="<p>Foulkes won the Democratic primary.</p>\r\n";
        chunks=new address[](2);
        vm.prank(alice); chunks[0]=store.storeChunk("<p>Foulkes won the Demo=");
        vm.prank(bob); chunks[1]=store.storeChunk("\r\ncratic primary.</p>\r\n");
        MarketFactory.CreateMarketParams memory cfg=defaultParams();cfg.contentField=HeadlineMarket.ContentField.Body;
        cfg.contentRegex="Foulkes won the Democratic primary";cfg.threshold=1;
        (market,)=factory.createMarket(cfg);
    }
    function test_SeparateUploadsAssembleAndSettle() public {
        (EmailProof memory p,address[] memory chunks,HeadlineMarket market)=proof();
        (bool ok,)=store.checkWithChunks(address(market),0,p,chunks);assertTrue(ok);
        vm.prank(settler);store.submitWithChunks(address(market),0,p,chunks);
        assertEq(uint256(market.resolution()),1);assertEq(ct.payoutNumerators(market.conditionId(),0),1);
        vm.expectRevert("Market: already resolved");store.submitWithChunks(address(market),0,p,chunks);
    }
    function test_ReorderedOrChangedChunksRejected() public {
        (EmailProof memory p,address[] memory chunks,HeadlineMarket market)=proof();
        (chunks[0],chunks[1])=(chunks[1],chunks[0]);(bool ok,)=store.checkWithChunks(address(market),0,p,chunks);assertFalse(ok);
        chunks[0]=store.storeChunk("forged text");(ok,)=store.checkWithChunks(address(market),0,p,chunks);assertFalse(ok);
    }
    function test_UnknownChunkOrDuplicateBodyInputRejected() public {
        (EmailProof memory p,address[] memory chunks,HeadlineMarket market)=proof();
        p.canonicalBody="forged";vm.expectRevert("BodyStore: body must be supplied by chunks");store.checkWithChunks(address(market),0,p,chunks);
        p.canonicalBody="";chunks[0]=alice;vm.expectRevert("BodyStore: unknown chunk");store.checkWithChunks(address(market),0,p,chunks);
    }
    function test_StoredCodeIsStoppedAndDeduplicated() public {
        address a=store.storeChunk(hex"fffeef");assertEq(a,store.storeChunk(hex"fffeef"));assertEq(a.code,hex"00fffeef");
        (bool ok,)=a.call("");assertTrue(ok);
    }
    function test_PageAndTotalLimits() public {
        vm.expectRevert("BodyStore: invalid chunk size");store.storeChunk(new bytes(24001));
        vm.expectRevert("BodyStore: invalid chunk size");store.storeChunk("");
        address a=store.storeChunk(new bytes(24000));address[] memory chunks=new address[](9);
        for(uint i;i<9;i++)chunks[i]=a;
        vm.expectRevert("BodyStore: body too large");store.assemble(chunks);
    }
}
