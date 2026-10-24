// Read-only geth-style tracer. Opcode costs come from gas deltas, not getCost().
export const SOURCE_GAS_TRACER = `{
  frames: [], stack: [], rows: [], tables: {}, steps: 0, errors: [],
  make: function(address, type, gas, parent) {
    var f = {id:this.frames.length,address:address,type:type,initialGas:gas,parent:parent,
      firstGas:null,previousGas:null,previousRow:null,pendingChildGas:0,childrenGas:0,
      exclusiveGas:0,steps:0,gasUsed:null};
    if(!this.tables[address]) this.tables[address]=[];
    f.table=this.tables[address];
    this.frames.push(f); this.stack.push(f.id); return f;
  },
  charge: function(f, cost) {
    if(cost < 0) throw new Error('Invalid exclusive cost '+cost);
    if(f.previousRow!==null) f.previousRow.gasCost += cost;
    else if(cost!==0) throw new Error('Unassigned opcode gas');
    f.exclusiveGas += cost;
  },
  finish: function(f, used) {
    f.gasUsed=used;
    if(f.steps>0) {
      this.charge(f, used-(f.firstGas-f.previousGas)-f.pendingChildGas);
      f.pendingChildGas=0;
    } else f.exclusiveGas=used;
    if(f.exclusiveGas+f.childrenGas!==used) throw new Error('Frame reconciliation failed');
  },
  enter: function(call) {
    if(this.stack.length===0) throw new Error('Missing root step');
    var f=this.make(toHex(call.getTo()),call.getType(),call.getGas(),this.stack[this.stack.length-1]);
    f.selector=toHex(call.getInput()).slice(0,10);
  },
  exit: function(result) {
    var f=this.frames[this.stack.pop()];
    this.finish(f,result.getGasUsed());
    f.error=result.getError();
    var p=this.frames[this.stack[this.stack.length-1]];
    p.pendingChildGas+=f.gasUsed; p.childrenGas+=f.gasUsed;
  },
  step: function(log, db) {
    if(++this.steps>60000000) throw new Error('Bounded tracer step limit exceeded');
    var gas=log.getGas();
    if(this.stack.length===0) this.make(toHex(log.contract.getAddress()),'ROOT',gas,null);
    var f=this.frames[this.stack[this.stack.length-1]];
    if(f.firstGas===null) f.firstGas=gas;
    if(f.previousGas!==null) {
      this.charge(f,f.previousGas-gas-f.pendingChildGas);
      f.pendingChildGas=0;
    }
    var pc=log.getPC(); var row=f.table[pc];
    if(!row) { row={address:f.address,pc:pc,op:log.op.toString(),count:0,gasCost:0};
      f.table[pc]=row; this.rows.push(row); }
    row.count++;
    f.previousGas=gas; f.previousRow=row; f.steps++;
  },
  fault: function(log, db) { this.errors.push({pc:log.getPC(),error:log.getError()}); },
  result: function(ctx, db) {
    if(this.stack.length!==1) throw new Error('Unclosed trace frames');
    var root=this.frames[this.stack[0]];
    var intrinsic=ctx.gas-root.firstGas;
    this.finish(root,ctx.gasUsed-intrinsic);
    var rows=this.rows;
    var opcodeGas=0; for(var i=0;i<rows.length;i++) opcodeGas+=rows[i].gasCost;
    var opaqueGas=0;
    for(var j=0;j<this.frames.length;j++) {
      if(this.frames[j].steps===0) opaqueGas+=this.frames[j].exclusiveGas;
      delete this.frames[j].table; delete this.frames[j].previousRow;
    }
    if(opcodeGas+opaqueGas+intrinsic!==ctx.gasUsed) throw new Error('Transaction reconciliation failed');
    return {schema:'peace-derived-exclusive-pc-gas-v1',gasUsed:ctx.gasUsed,intrinsicGas:intrinsic,
      opcodeGas:opcodeGas,opaqueCallGas:opaqueGas,steps:this.steps,frames:this.frames,rows:rows,
      errors:this.errors,method:'Same-frame gas deltas minus child frame gasUsed; terminal gas reconciled to frame total. getCost() is not used.'};
  }
}`;
