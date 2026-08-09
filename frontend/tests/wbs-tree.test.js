const assert = require("node:assert/strict");
const tree = require("../js/wbs-tree.js");

function node(id, parent, order, depth=1) { return {id, parent_id:parent, sort_order:order, depth, code:id}; }

let base = [node("A",null,1000),node("B",null,2000),node("C",null,3000)];
let r = tree.moveUp(base,"B");
assert.equal(r.changed,true); assert.deepEqual(r.nodes.filter(n=>!n.parent_id).sort((a,b)=>a.sort_order-b.sort_order).map(n=>n.id),["B","A","C"]);
r = tree.moveDown(base,"B");
assert.deepEqual(r.nodes.filter(n=>!n.parent_id).sort((a,b)=>a.sort_order-b.sort_order).map(n=>n.id),["A","C","B"]);
r = tree.moveUp(base,"A"); assert.equal(r.changed,false);
r = tree.indent(base,"B"); assert.equal(r.changed,true); assert.equal(r.nodes.find(n=>n.id==="B").parent_id,"A"); assert.equal(r.nodes.find(n=>n.id==="B").depth,2);
r = tree.outdent(r.nodes,"B"); assert.equal(r.changed,true); assert.equal(r.nodes.find(n=>n.id==="B").parent_id,null);

let subtree=[node("A",null,1000),node("B",null,2000),node("C","B",1000,2)];
r=tree.indent(subtree,"B"); assert.equal(r.nodes.find(n=>n.id==="B").depth,2); assert.equal(r.nodes.find(n=>n.id==="C").depth,3);

let deep=[node("L1",null,1000),node("L2","L1",1000,2),node("L3","L2",1000,3),node("L4","L3",1000,4),node("L5","L4",1000,5),node("L6A","L5",1000,6),node("L6B","L5",2000,6)];
r=tree.indent(deep,"L6B"); assert.equal(r.changed,false); assert.match(r.error,/6 levels/);

console.log("WBS tree interaction tests passed");
