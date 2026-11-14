import assert from 'node:assert/strict';
import {maskSuggestions,moveMask} from './frontend/card-import/masking.mjs';
import {uploadSets} from './frontend/card-import/save.mjs';
import {applyCourseFields,parseCardDate,readCourseFields,reviewSides,updateCalculatedExpiry,workerPdfName} from './frontend/card-import/fields.mjs';

const text='FIN F1234567N';
const symbols=Array.from(text,(char,i)=>({text:char,x:(10+i*3)/100,y:.2,width:.02,height:.04})).filter(s=>s.text!==' ');
const {boxes,uncertain}=maskSuggestions([{text,symbols}]);
assert.equal(uncertain,false);
assert.equal(boxes.length,1);
assert.equal(boxes[0].x,.22);
assert.ok(boxes[0].x+boxes[0].w<symbols.at(-4).x);
assert.ok(!('suffix' in boxes[0]));
assert.deepEqual(maskSuggestions([{text}]),{boxes:[],uncertain:true});
assert.deepEqual(maskSuggestions([{text:'DOB 12/03/1990'}]),{boxes:[],uncertain:false});
assert.equal(moveMask(boxes[0],'move',.25,.1).x,.47);
assert.ok(moveMask(boxes[0],'se',.04,.02).w>boxes[0].w);
assert.equal(moveMask(boxes[0],'nw',-2,-2).x,0);

const front=['CERTIFICATE OF COMPLETION','Course Title: WORKPLACE SAFETY','AND HEALTH FOR SUPERVISORS','Training Provider: Vortex Training Centre','Employer: Another Company','Date of Issue: 29 Feb 2024'];
const back=['Valid for 2 years from','the date of issue'];
const headingFields=readCourseFields(['EVERSAFE ACADEMY','Course Title: WORK AT HEIGHT','Issued Dawe: 14/04/2023']);
assert.equal(headingFields.institute.value,'EVERSAFE ACADEMY');
assert.equal(headingFields.institute.review,true);
assert.equal(headingFields.issued_date.value,'2023-04-14');
const provider=readCourseFields(['EFG TRAINING','MWSHCS-04-EFG17','Si','SERVICES PRIVATE LTD','COURSE TITLE: MANAGE WORKPLACE SAFETY AND HEALTH IN','CONSTRUCTION SITES','CS CODE','ISSUED DATE.','13-Sep-2026']);
assert.equal(provider.institute.value,'EFG TRAINING SERVICES PRIVATE LTD');
assert.equal(provider.title.value,'MANAGE WORKPLACE SAFETY AND HEALTH IN\nCONSTRUCTION SITES');
assert.equal(provider.issued_date.value,'2026-09-13');
const card={};
applyCourseFields(card,readCourseFields(front,back));
assert.equal(card.title,'WORKPLACE SAFETY\nAND HEALTH FOR SUPERVISORS');
assert.equal(card.institute,'Vortex Training Centre');
assert.equal(card.issued_date,'2024-02-29');
assert.equal(card.expiry_date,'2026-02-28');
assert.equal(card.ocrFields.period.sources[0].side,'Back');
card.issued_date='2025-01-13';
updateCalculatedExpiry(card);
assert.equal(card.expiry_date,'2027-01-13');
card.editedFields={expiry_date:true,institute:true};
card.institute='Confirmed Provider';
card.expiry_date='2028-04-15';
applyCourseFields(card,readCourseFields(front,back));
assert.equal(card.expiry_date,'2028-04-15');
assert.equal(card.institute,'Confirmed Provider');
assert.equal(readCourseFields(front,['Valid Until: 30 Jun 2027',...back]).expiry_date.value,'2027-06-30');
assert.equal(readCourseFields(['Training date: 29 Feb 2024'],back).issued_date.value,'');
assert.equal(readCourseFields(front,['Date of Issue: 20 Mar 2024']).issued_date.review,true);
assert.equal(parseCardDate('02/03/2025'),'');
assert.equal(parseCardDate('2025-03-02'),'2025-03-02');
assert.equal(workerPdfName('Renganathan / Anbazhagan'),'RENGANATHAN_ANBAZHAGAN_Worker_Cards.pdf');

const crop={number:1,title:'Course',jpeg:'data:image/jpeg;base64,YWJj',maskReviewed:true};
const course={front:{...crop},back:{...crop,maskReviewed:false}};
const permit={front:{...crop,number:2,category:'work_permit',issued_date:'2025-06-12'},back:{...crop,maskReviewed:false}};
assert.deepEqual(reviewSides(course),[course.front]);
assert.deepEqual(reviewSides(permit),[permit.front,permit.back]);
assert.deepEqual(reviewSides({front:permit.front}),[permit.front]);
let uploads=0,patches=0,failOnce=true;
const saved=new Map(),details=new Map();
const bridge={upload:async(side,bytes,plan,record,id)=>{
  uploads++;
  assert.equal(JSON.parse(plan).pages[0].reviewed,true);
  const result=saved.get(id)||{id,updated_at:'v1'};
  saved.set(id,result);
  if(failOnce&&side==='front'){failOnce=false;throw Error('Response lost after save');}
  return result;
},details:async(r,fields)=>{patches++;details.set(r.id,fields);return r;}};
await assert.rejects(()=>uploadSets([permit],bridge,()=>{}),/Review the required sides/);
await assert.rejects(()=>uploadSets([course,permit],bridge,()=>{},{reviewed:true}),/1 of 2 saved.*Response lost/);
assert.equal(saved.size,2);
assert.equal(details.get(permit.front.importId).issued_date,null);
await uploadSets([course,permit],bridge,()=>{},{reviewed:true});
assert.equal(saved.size,2);
assert.equal(uploads,5);
assert.equal(patches,2);
await uploadSets([course,permit],bridge,()=>{},{reviewed:true});
assert.equal(uploads,5);
assert.equal(patches,2);
await assert.rejects(()=>uploadSets([{back:crop}],bridge,()=>{}),/front/);
console.log('PASS: FIN geometry, mask movement and resizing, date evidence, review rules, retry and PDF naming');

const {isWorkPermitFront}=await import('./frontend/card-import/fields.mjs');
const sPass=['S PASS','S Pass No. 0 1234567',{text:'K1234567',x:.82,y:.91}];
assert.equal(isWorkPermitFront(sPass),true);
assert.equal(isWorkPermitFront(['Course Title: Permit to Work']),false);
assert.equal(reviewSides({front:{title:'S Pass'},back:{}}).length,2);
const permitFields=readCourseFields(sPass,['VISIT PASS','Issued Date: 05/04/2026'],{workPermit:true});
assert.equal(permitFields.cert_no.value,'K1234567');
assert.equal(permitFields.issued_date.value,'');
assert.equal(readCourseFields(['S PASS','S Pass No. 0 1234567'],[],{workPermit:true}).cert_no.value,'');

const supervisor={};
applyCourseFields(supervisor,readCourseFields([
 'EVERSAFE ACADEMY','Serial Number: 001-00002',
 'Course Title: Workplace Safety and Health Management',
 'IN PROCESS PLANT','(PIW-PRO-1234-1.1-E)','Name: Sample Learner','Issued Date: 14/04/2023'
],['6. This card will expire Not Applicable']));
assert.equal(supervisor.cert_no,'001-00002');
assert.match(supervisor.title,/\(PIW-PRO-1234-1\.1-E\)$/);
assert.equal(supervisor.no_expiry,true);
assert.equal(supervisor.expiry_date,'');
assert.equal(readCourseFields(front,['6. TSC Title/Code: Not Applicable']).no_expiry.value,'');

const workerCourse={};
const courseFront=['Course Title: Perform Work in Confined Space Operation','Issued Date: 03/08/2023'];
const courseBack=['This card will expire 3 Years From Last Date Of Course'];
applyCourseFields(workerCourse,readCourseFields(courseFront,courseBack));
assert.equal(workerCourse.issued_date,'2023-08-03');
assert.equal(workerCourse.expiry_date,'');
assert.equal(workerCourse.no_expiry,false);
workerCourse.course_end_date='2023-08-01';
updateCalculatedExpiry(workerCourse);
assert.equal(workerCourse.expiry_date,'2026-08-01');

const dynamic={};
applyCourseFields(dynamic,readCourseFields([
 'Dynamic Safety Pte Ltd','S/N: DS-SOC-TUN-0001',
 'Course Title: Safety Orientation Course (Tunneling) For Workers',
 '(TSC Title/Code): NA','Issued Date: 29/7/2026','Expiry Date: 28/7/2028'
],['This card is validity: As per this card front page.']));
assert.equal(dynamic.institute,'Dynamic Safety Pte Ltd');
assert.equal(dynamic.cert_no,'DS-SOC-TUN-0001');
assert.equal(dynamic.title,'Safety Orientation Course (Tunneling) For Workers');
assert.equal(dynamic.expiry_date,'2028-07-28');

const efg={};
applyCourseFields(efg,readCourseFields([
 'EFG TRAINING SERVICES','PRIVATE LTD','Serial Number','AC-PRO-00001',
 'COURSE TITLE: APPLY WORKPLACE SAFETY AND HEALTH IN','PROCESS PLANT','CS CODE: ABC-001',
 'ISSUED DATE: 22-Jul-2026'
],['This card is valid for 3 years from the date of issue.']));
assert.equal(efg.institute,'EFG TRAINING SERVICES PRIVATE LTD');
assert.equal(efg.cert_no,'AC-PRO-00001');
assert.equal(efg.title,'APPLY WORKPLACE SAFETY AND HEALTH IN\nPROCESS PLANT');
assert.equal(efg.expiry_date,'2029-07-22');
assert.equal(readCourseFields(['Training Provider: Aster Learning','Course Title: Working at Height']).institute.value,'Aster Learning');
assert.equal(readCourseFields(['Cedar Skills Pte Ltd','Course Title: Working at Height']).institute.value,'Cedar Skills Pte Ltd');
assert.equal(maskSuggestions([{text:'ID No.: F1234567N',symbols}]).boxes.length,1);
assert.equal(maskSuggestions([{text:'ID: 567N'}]).uncertain,true);
console.log('PASS: five card layouts, unfamiliar providers, date basis, and ID labels');
