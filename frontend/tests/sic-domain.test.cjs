const {test}=require('node:test');const assert=require('node:assert/strict');const S=require('../js/sic-domain.js');
test('expiry follows calendar months, clamps month end and subtracts one day',()=>{assert.equal(S.expiry('2026-10-16',12),'2027-10-15');assert.equal(S.expiry('2024-02-29',12),'2025-02-27');assert.equal(S.expiry('2026-01-31',1),'2026-02-27');assert.equal(S.expiry('2026-12-31',6),'2027-06-29');assert.equal(S.expiry('2026-02-30',6),'');assert.equal(S.expiry('2026-10-16',0),'')});
test('expiry is inclusive with non-overlapping status boundaries',()=>{assert.equal(S.status('2026-10-15','2026-10-16'),'Expired');assert.equal(S.status('2026-10-16','2026-10-16'),'Expiring Soon');assert.equal(S.status('2026-11-15','2026-10-16'),'Expiring Soon');assert.equal(S.status('2026-11-16','2026-10-16'),'Valid')});
const rows=Array.from({length:123},(_,i)=>({id:String(i).padStart(3,'0'),name:'Worker '+i,fin:'F'+i,site_name:i%2?'Beta':'Alpha',site_id:i%2?'b':'a',sic_date:'2026-01-01',expiry_date:i%3?'2027-01-01':'2026-10-15',worker_status:i%5?'active':'inactive',card_count:i%2,archived:i%7===0}));
test('filters retain all matching records beyond a visible page',()=>{const result=S.filter(rows,{worker:'all',archive:'all'},'2026-10-16');assert.equal(result.length,123);assert.equal(S.filter(rows,{site:'a',status:'Expired',worker:'all',archive:'all'},'2026-10-16').length,21)});
test('worker/archive/card and date filters compose',()=>{const result=S.filter(rows,{worker:'active',archive:'current',card:'missing',sicFrom:'2026-01-01',expiryTo:'2026-10-16'},'2026-10-16');assert.ok(result.length>0);assert.ok(result.every(r=>r.worker_status==='active'&&!r.archived&&!r.card_count&&r.expiry_date<='2026-10-16'))});
test('Excel values cannot become formulas',()=>{assert.equal(S.excelText('=1+1'),"'=1+1");assert.equal(S.excelText('@SUM(A1)'),"'@SUM(A1)");assert.equal(S.excelText('Anbu'),'Anbu')});

test('site choices hide an unused archived duplicate and retain independent archived sites or linked history',()=>{const sites=[{id:'active',site_name:'TUAS LOT',status:'active'},{id:'old',site_name:' tuas  lot ',status:'archived'},{id:'advario',site_name:'ADVARIO',status:'archived'}];assert.deepEqual(S.siteChoices(sites).map(s=>s.id),['active','advario']);assert.deepEqual(S.siteChoices(sites,[{site_id:'old'}]).map(s=>s.id),['active','old','advario']);assert.deepEqual(S.siteChoices([sites[1]]).map(s=>s.id),['old'])});

test('removed sites stay out of new choices but retain linked history',()=>{const s={id:'gone',site_name:'OLD',status:'archived',removed_at:'2026-10-16'};assert.deepEqual(S.siteChoices([s]),[]);assert.deepEqual(S.siteChoices([s],[{site_id:'gone'}]),[s])});
test('dashboard shortcuts intersect date filters and include expiry today',()=>{
 const rows=[{id:'a',name:'A',expiry_date:'2026-10-20'},{id:'b',name:'B',expiry_date:'2026-10-21'},{id:'c',name:'C',expiry_date:'2026-10-28'},{id:'d',name:'D',expiry_date:'2026-11-20'},{id:'e',name:'E',expiry_date:'2026-11-21'},{id:'f',name:'F',expiry_date:'2026-12-20'},{id:'g',name:'G',expiry_date:'2026-12-21'}];
 const now='2026-10-21',ids=view=>S.filter(rows,S.dashboardSelection({},view,now),now).map(r=>r.id);
 assert.deepEqual(ids('urgent'),['a','b','c','d']);assert.deepEqual(ids('7'),['b','c']);assert.deepEqual(ids('30'),['b','c','d']);assert.deepEqual(ids('60'),['b','c','d','e','f']);assert.deepEqual(ids('expired'),['a']);assert.deepEqual(ids('valid'),['e','f','g']);
 assert.deepEqual(S.dashboardSelection({expiryFrom:'2026-11-01',expiryTo:'2026-11-10',site:'s'},'30',now),{expiryFrom:'2026-11-01',expiryTo:'2026-11-10',site:'s'});
 assert.equal(S.filter(rows,S.dashboardSelection({expiryFrom:'2026-12-01'},'7',now),now).length,0);
});
test('dashboard counts distinct workers separately from SIC records and ranks sites by urgency',()=>{
 const rows=[{worker_id:'a',site_id:'b',site_name:'Beta',expiry_date:'2026-11-01'},{worker_id:'a',site_id:'a',site_name:'Alpha',expiry_date:'2026-10-01'},{worker_id:'b',site_id:'c',site_name:'Charlie',expiry_date:'2027-01-01'},{worker_id:'c',site_id:'a',site_name:'Alpha',expiry_date:'2026-10-02'}];
 const summary=S.dashboardSummary(rows,'2026-10-21');assert.deepEqual(summary.counts,{workers:3,records:4,valid:1,soon:1,expired:2});assert.deepEqual(summary.sites.map(s=>s.id),['a','b','c']);assert.equal(summary.sites[0].expired,2);assert.deepEqual(S.dashboardSummary([],'2026-10-21').sites,[]);
});
test('recent activity sorts newest records first without losing tie stability',()=>{
 const rows=[{id:'a',name:'A',created_at:'2026-10-01'},{id:'c',name:'C',created_at:'2026-10-20'},{id:'b',name:'B',created_at:'2026-10-20'}];assert.deepEqual(S.filter(rows,{sort:'created_at'}).map(r=>r.id),['b','c','a']);
});
test('designation options preserve the agreed combined roles and acronyms',()=>{
 assert.deepEqual(S.designations,['General Worker','Welder','Rigger & Signalman','Lifting Supervisor','Supervisor','CS Supervisor','WAH Supervisor','Safety Supervisor','Driver','Lorry Crane Operator','Traffic Controller & Banksman','Fire Watchman']);
 assert.equal(S.designationChoice('  wah   supervisor  '),'WAH Supervisor');assert.equal(S.designationChoice('Confined Space Supervisor'),null);assert.equal(S.designationLabel(null),'Not specified');
});
test('designation search and filters distinguish missing data from custom names',()=>{
 const rows=[{id:'1',name:'One',designation:null},{id:'2',name:'Two',designation:'Welder'},{id:'3',name:'Three',designation:'missing'},{id:'4',name:'Four',designation:'Pipe Fitter'}];
 assert.deepEqual(S.filter(rows,{designation:'missing'}).map(r=>r.id),['1']);assert.deepEqual(S.filter(rows,{designation:'value:missing'}).map(r=>r.id),['3']);assert.deepEqual(S.filter(rows,{designation:'value:Pipe Fitter'}).map(r=>r.id),['4']);assert.deepEqual(S.filter(rows,{q:'welder'}).map(r=>r.id),['2']);assert.equal(S.excelText('=unsafe'),"'=unsafe");
});
