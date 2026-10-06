import assert from "node:assert/strict";
import { test } from "node:test";
import { toFunctionSelector, zeroAddress } from "viem";
import {
  FEE_SCALE, formatFeePercent, parseFeePercent, readPoolFeeConfiguration,
  readProtocolFeeConfiguration, validateTradingFees,
} from "../src/lib/fees.ts";

const address = "0x1111111111111111111111111111111111111111";
const treasury = "0x2222222222222222222222222222222222222222";
const implementation = "0x3333333333333333333333333333333333333333";
const code = (...signatures) => `0x${signatures.map((s) => `63${toFunctionSelector(s).slice(2)}14`).join("")}00`;
const legacyPool = code("fee()", "calcBuyAmount(uint256,uint256)", "calcSellAmount(uint256,uint256)");
const legacyFactory = code("marketCount()", "getAllMarkets()");
const platform = code("fee()", "protocolFee()", "feeRecipient()", "totalFee()");
const clone = `0x363d3d373d3d3d363d73${implementation.slice(2)}5af43d82803e903d91602b57fd5bf3`;
function client(bytecode = platform, responses = {}) {
  const values = { protocolFee: 22n * 10n ** 15n, feeRecipient: treasury, totalFee: 42n * 10n ** 15n, ...responses };
  return {
    getBytecode: async () => bytecode,
    readContract: async ({ functionName }) => {
      const value = values[functionName];
      if (value instanceof Error) throw value;
      return value;
    },
  };
}

test("percentage parsing and formatting use exact 1e18 rates", () => {
  assert.equal(parseFeePercent("2.2"), 22n * 10n ** 15n);
  assert.equal(parseFeePercent(" 2 "), 2n * 10n ** 16n);
  assert.equal(parseFeePercent(".5"), 5n * 10n ** 15n);
  assert.equal(parseFeePercent("0"), 0n);
  assert.equal(parseFeePercent("0.0000000000000001"), 1n);
  assert.equal(parseFeePercent("99.9999999999999999"), FEE_SCALE - 1n);
  assert.equal(formatFeePercent(42n * 10n ** 15n), "4.2");
  assert.equal(formatFeePercent(0n), "0");
  assert.equal(formatFeePercent(1n), "0.0000000000000001");
});

test("invalid, negative, over-precision and 100% inputs are rejected", () => {
  for (const value of ["", " ", ".", "-1", "NaN", "Infinity", "2e0", "2abc", "2,2", "100", "101", "0.00000000000000001"]) {
    assert.equal(parseFeePercent(value), null, value);
  }
});

test("combined fee must be strictly below 100%, including exact boundary", () => {
  const operator = parseFeePercent("2.2");
  assert.equal(validateTradingFees(parseFeePercent("2"), operator), null);
  assert.equal(validateTradingFees(parseFeePercent("0"), operator), null);
  assert.equal(validateTradingFees(parseFeePercent("97.7999999999999999"), operator), null);
  assert.match(validateTradingFees(parseFeePercent("97.8"), operator), /less than 100%/);
  assert.match(validateTradingFees(parseFeePercent("99"), operator), /less than 100%/);
  assert.match(validateTradingFees(null, operator), /Enter an LP fee/);
});

test("new pool rates come from all three onchain getters", async () => {
  assert.deepEqual(await readPoolFeeConfiguration(client(), address, [], parseFeePercent("2")), {
    protocolFee: parseFeePercent("2.2"), feeRecipient: treasury, legacy: false, totalFee: parseFeePercent("4.2"),
  });
});

test("zero LP pools retain the full operator fee", async () => {
  const result = await readPoolFeeConfiguration(client(platform, { totalFee: parseFeePercent("2.2") }), address, [], 0n);
  assert.equal(result.totalFee, parseFeePercent("2.2"));
});

test("verified legacy factory is fee-free without invoking absent getters", async () => {
  const reader = client(legacyFactory);
  reader.readContract = async () => { throw new Error("must not call a missing getter"); };
  assert.deepEqual(await readProtocolFeeConfiguration(reader, address, [], "factory"), {
    protocolFee: 0n, feeRecipient: zeroAddress, legacy: true,
  });
});

test("legacy EIP-1167 pool is identified by its implementation, retaining LP fee", async () => {
  const reader = client();
  reader.getBytecode = async ({ address: target }) => target === address ? clone : legacyPool;
  reader.readContract = async () => { throw new Error("must not call a missing getter"); };
  assert.deepEqual(await readPoolFeeConfiguration(reader, address, [], parseFeePercent("2")), {
    protocolFee: 0n, feeRecipient: zeroAddress, legacy: true, totalFee: parseFeePercent("2"),
  });
});

test("platform EIP-1167 pool reads its new getters", async () => {
  const reader = client();
  reader.getBytecode = async ({ address: target }) => target === address ? clone : platform;
  const config = await readPoolFeeConfiguration(reader, address, [], parseFeePercent("2"));
  assert.equal(config.protocolFee, parseFeePercent("2.2"));
  assert.equal(config.legacy, false);
});

test("bytecode RPC failure is not a zero fee and can recover on retry", async () => {
  const reader = client();
  let fail = true;
  reader.getBytecode = async () => { if (fail) throw new Error("RPC timeout"); return platform; };
  await assert.rejects(readProtocolFeeConfiguration(reader, address, [], "pool"), /RPC timeout/);
  fail = false;
  assert.equal((await readProtocolFeeConfiguration(reader, address, [], "pool")).protocolFee, parseFeePercent("2.2"));
});

for (const getter of ["protocolFee", "feeRecipient", "totalFee"]) {
  test(`${getter} RPC/multicall failure is never interpreted as a legacy fee`, async () => {
    const reader = client(platform, { [getter]: new Error("multicall HTTP 503") });
    await assert.rejects(readPoolFeeConfiguration(reader, address, [], parseFeePercent("2")), /multicall HTTP 503/);
  });
}

test("no contract, unknown proxies, and incomplete fee interfaces fail closed", async () => {
  for (const bytecode of [undefined, "0x", "0x600036", code("protocolFee()"), code("feeRecipient()")]) {
    const reader = client();
    reader.getBytecode = async () => bytecode;
    await assert.rejects(readProtocolFeeConfiguration(reader, address, [], "pool"));
  }
});

test("missing or failed EIP-1167 implementation is not treated as legacy", async () => {
  const reader = client();
  reader.getBytecode = async ({ address: target }) => target === address ? clone : undefined;
  await assert.rejects(readProtocolFeeConfiguration(reader, address, [], "pool"), /implementation code is unavailable/);
});

test("bad onchain recipient and invalid or inconsistent fee rates are rejected", async () => {
  for (const responses of [
    { feeRecipient: zeroAddress }, { feeRecipient: "bad-address" }, { protocolFee: FEE_SCALE },
    { protocolFee: -1n }, { protocolFee: "22000000000000000" }, { totalFee: parseFeePercent("2") },
  ]) {
    await assert.rejects(readPoolFeeConfiguration(client(platform, responses), address, [], parseFeePercent("2")));
  }
});

test("a supported zero-rate factory is not mislabeled as legacy", async () => {
  assert.deepEqual(await readProtocolFeeConfiguration(client(platform, { protocolFee: 0n, feeRecipient: zeroAddress }), address, [], "factory"), {
    protocolFee: 0n, feeRecipient: zeroAddress, legacy: false,
  });
});
