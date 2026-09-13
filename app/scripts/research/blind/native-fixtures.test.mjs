import {test} from 'node:test';
import assert from 'node:assert/strict';
import {classify,summarize} from './native-fixtures.mjs';
test('gas failure never counts as safe negative or positive success',()=>{
  const calls=[{matched:false},{error:'OutOfGas'}];
  assert.deepEqual(classify('neither',calls),{scorable:false,passed:false,falsePositive:false});
  const rows=[{expected:'neither',...classify('neither',calls)},{expected:'A',...classify('A',[{matched:true},{error:'OutOfGas'}])}];
  assert.deepEqual(summarize(rows),{fixtures:2,positivePasses:0,positiveTotal:1,negativeFalsePositives:0,negativeTotal:1,unscorablePositives:1,unscorableNegatives:1});
});
test('a known false match remains a false positive if the other call fails',()=>{
  assert.deepEqual(classify('neither',[{matched:true},{error:'OutOfGas'}]),{scorable:false,passed:false,falsePositive:true});
});
