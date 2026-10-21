const {test}=require('node:test');
const assert=require('node:assert/strict');
const C=require('../js/sic-card-data.js');
test('labelled fields preserve printed dates, reference and issuer',()=>{
  const f=C.parse('SITE INDUCTION COURSE\nName: TEST WORKER\nFIN: G1234567X\nSite: CCP3\nSIC Date: 01/10/2026\nExpiry Date: 30 Sep 2027\nValidity: 1 year\nCard No: SIC-123\nIssued by: SITE OFFICE');
  assert.deepEqual(f,{fin:['G1234567X'],name:['TEST WORKER'],site:['CCP3'],reference:['SIC-123'],issuer:['SITE OFFICE'],sic_date:['2026-10-01'],expiry_date:['2027-09-30'],validity_months:[12]});
});
test('malformed and ambiguous dates are not invented',()=>{
  for(const s of ['29/02/2025','31/04/2026','2026-13-01','1/2/26','01/01/0001'])assert.equal(C.date(s),'');
  assert.equal(C.date('29-Feb-2024'),'2024-02-29');
  assert.deepEqual(C.parse('Induction: 01/10/2026\nSIC Date: 02/10/2026').sic_date,['2026-10-01','2026-10-02']);
  assert.deepEqual(C.parse('DOB: 01/01/1990\nDate: 01/01/2026').sic_date,[]);
});
test('FIN takes precedence over name and duplicate matches remain unresolved',()=>{
  const workers=[{id:'a',name:'TEST WORKER',fin:'G1234567X',status:'active'},{id:'b',name:'TEST WORKER',fin:'M7654321Y',status:'active'}];
  assert.equal(C.matchWorker(C.parse('Name: TEST WORKER'),workers),null);
  assert.equal(C.matchWorker(C.parse('FIN: G1234567X'),workers).id,'a');
  assert.equal(C.matchWorker(C.parse('Name: TEST WORKER\nFIN: F1111111X'),workers),null);
  assert.equal(C.matchWorker(C.parse('FIN: G1234567X\nFIN: M7654321Y'),workers),null);
});
test('site matching is exact and ambiguity is preserved',()=>{
  const sites=[{id:'a',site_name:'CCP3'},{id:'b',site_name:'CCP30'}];
  assert.equal(C.matchSite(C.parse('Site: CCP3'),sites).id,'a');
  assert.equal(C.matchSite(C.parse('Site: CCP'),sites),null);
  assert.equal(C.matchSite(C.parse('Site: CCP3'),[sites[0],{id:'c',site_name:'CCP3'}]),null);
});
test('front/back pages combine, separate workers stay separate, mixed PDFs require splitting',()=>{
  const parts=[{fileIndex:0,page:1,text:'FIN: G1234567X\nName: A'},{fileIndex:1,page:1,text:'FIN: G1234567X\nExpiry Date: 30/09/2027'},{fileIndex:2,page:1,text:'FIN: M7654321Y\nName: B'}];
  const ds=C.drafts(parts);assert.equal(ds.length,2);assert.deepEqual(ds[0].fileIndexes,[0,1]);assert.deepEqual(ds[0].fields.expiry_date,['2027-09-30']);
  assert.equal(C.drafts([{fileIndex:0,text:'FIN: G1234567X'},{fileIndex:0,text:'FIN: M7654321Y'}])[0].mixed,true);
  assert.equal(C.drafts([{fileIndex:0,text:'FIN: G1234567X'},{fileIndex:1,text:'Expiry Date: 30/09/2027'}]).length,1);
});
test('name-only back joins a front with the same unambiguous name and FIN',()=>{
  const ds=C.drafts([{fileIndex:0,text:'FIN: G1234567X\nName: TEST WORKER'},{fileIndex:1,text:'Name: TEST WORKER\nExpiry Date: 30/09/2027'}]);
  assert.equal(ds.length,1);assert.deepEqual(ds[0].fileIndexes,[0,1]);
});
test('a unique name can match a worker with no directory FIN while preserving card FIN',()=>{
  const fields=C.parse('Name: TEST WORKER\nFIN: G1234567X');
  assert.equal(C.matchWorker(fields,[{id:'a',name:'TEST WORKER',fin:null,status:'active'}]).id,'a');
  assert.equal(C.matchWorker(fields,[{id:'a',name:'TEST WORKER',fin:'M7654321Y',status:'active'}]),null);
});
