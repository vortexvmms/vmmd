/* End-Time Verification exports. No requests or mutations of attendance data. */
(function(root){'use strict';
const HEADERS=['SN','DATE','WORKER ID','NAME','SITE','STATUS','START','END TIME','NORMAL h','OT h','SUBMITTED'];
const status=r=>r.present?'Present':({mc:'MC',al:'AL',ul:'UL',absent:'Absent'}[r.absence_type]||'Absent');
const number=v=>Number.isFinite(Number(v))?Number(v):0;
const dmy=d=>/^\d{4}-\d{2}-\d{2}$/.test(d)?d.split('-').reverse().join('/'):d;
function data(rows,date){return rows.map((r,i)=>[i+1,dmy(date),r.worker_code||'',r.worker_name||'',r.site_name||'',status(r),r.present?(r.start_time||''):'',r.present?(r.end_time||'Missing'):'',r.present?number(r.normal_hours):'',r.present?number(r.ot_hours):'',r.submitted?'Yes':'Pending'])}
function csvCell(v){let s=String(v??'');if(typeof v==='string'&&(/^[\s]*[=+\-@]/.test(s)||/^[\t\r\n]/.test(s)))s="'"+s;return '"'+s.replace(/"/g,'""')+'"'}
function csv(rows,date){return '\ufeff'+[HEADERS,...data(rows,date)].map(r=>r.map(csvCell).join(',')).join('\r\n')+'\r\n'}
function time(v){const m=/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/.exec(v||'');if(!m||+m[1]>24||+m[2]>59||+(m[3]||0)>59)return null;return (+m[1]*3600+ +m[2]*60+ +(m[3]||0))/86400}
function workbook(ExcelJS,rows,context){
 const wb=new ExcelJS.Workbook();wb.creator=context.user||'VCMS';wb.created=new Date();wb.calcProperties.fullCalcOnLoad=true;
 const ws=wb.addWorksheet('End-Time Verification',{views:[{state:'frozen',ySplit:8,xSplit:3,showGridLines:false}],pageSetup:{paperSize:9,orientation:'landscape',fitToPage:true,fitToWidth:1,fitToHeight:0,printTitlesRow:'1:8',margins:{left:.25,right:.25,top:.3,bottom:.4,header:.15,footer:.2}}});
 const ink='FF17243B',red='FFC00000',line='FFD6DCE5';
 function merged(row,text,size=10,color=ink){ws.mergeCells(row,1,row,11);const c=ws.getCell(row,1);c.value=text;c.font={name:'Arial',size,bold:row<=2,color:{argb:color}};c.alignment={vertical:'middle',wrapText:true};ws.getRow(row).height=row===1?25:row===2?24:23}
 merged(1,'VORTEX ENGINEERING PTE LTD',16,red);merged(2,'END-TIME VERIFICATION',13);
 merged(3,`Date: ${dmy(context.date)}    |    Site: ${context.site||'All sites'}`);
 merged(4,'Filters: '+(context.filters||'All workers')+'    |    Sort: '+(context.sort||'Site'));
 merged(5,`Checked by: ${context.user||'—'}    |    Generated: ${context.generated||''} SGT`);
 const present=rows.filter(r=>r.present).length,missing=rows.filter(r=>r.present&&!r.end_time).length,pending=rows.filter(r=>!r.submitted).length;
 merged(6,`${rows.length} records    |    ${present} present    |    ${missing} missing end times    |    ${pending} pending submissions`);
 ws.getRow(7).height=8;ws.getRow(8).values=HEADERS;ws.getRow(8).height=26;
 ws.getRow(8).eachCell(c=>{c.font={name:'Arial',size:9,bold:true,color:{argb:'FFFFFFFF'}};c.fill={type:'pattern',pattern:'solid',fgColor:{argb:ink}};c.alignment={vertical:'middle',horizontal:'center',wrapText:true}});
 data(rows,context.date).forEach((values,i)=>{
  const source=rows[i],n=i+9;values[1]=new Date(context.date+'T00:00:00Z');
  for(const index of [6,7]){if(source.present&&values[index]&&values[index]!=='Missing'){const t=time(values[index]);if(t!==null)values[index]=t}}
  const row=ws.getRow(n);row.values=values;row.height=22;
  row.eachCell({includeEmpty:true},(c,column)=>{c.font={name:'Arial',size:10,color:{argb:source.present?ink:'FF667085'}};c.alignment={vertical:'middle',horizontal:[1,2,6,7,8,11].includes(column)?'center':[9,10].includes(column)?'right':'left',wrapText:[4,5].includes(column)};c.border={bottom:{style:'hair',color:{argb:line}}};if(i%2)c.fill={type:'pattern',pattern:'solid',fgColor:{argb:'FFF3F5F8'}}});
  if(source.present&&!source.end_time){const c=row.getCell(8);c.fill={type:'pattern',pattern:'solid',fgColor:{argb:'FFFEE2E2'}};c.font={name:'Arial',size:10,bold:true,color:{argb:'FFB91C1C'}}}
  if(!source.submitted)row.getCell(11).fill={type:'pattern',pattern:'solid',fgColor:{argb:'FFFEF3C7'}};
 });
 const end=rows.length+8,total=end+1;ws.mergeCells(total,1,total,8);ws.getCell(total,1).value=`TOTAL (${present} present)`;
 for(const [column,key] of [[9,'normal_hours'],[10,'ot_hours']])ws.getCell(total,column).value=rows.length?{formula:`SUM(${column===9?'I':'J'}9:${column===9?'I':'J'}${end})`,result:rows.reduce((sum,r)=>sum+(r.present?number(r[key]):0),0)}:0;
 ws.getRow(total).height=25;ws.getRow(total).eachCell({includeEmpty:true},c=>{c.font={name:'Arial',size:10,bold:true,color:{argb:ink}};c.fill={type:'pattern',pattern:'solid',fgColor:{argb:'FFE2E8F0'}};c.border={top:{style:'thin',color:{argb:ink}}};c.alignment={vertical:'middle',horizontal:c.col>=9?'right':'left'}});
 [6,13,16,36,25,13,11,12,11,11,13].forEach((width,i)=>ws.getColumn(i+1).width=width);ws.getColumn(2).numFmt='dd/mm/yyyy';[7,8].forEach(c=>ws.getColumn(c).numFmt='[h]:mm');[9,10].forEach(c=>ws.getColumn(c).numFmt='0.0');
 ws.autoFilter={from:'A8',to:'K'+end};ws.pageSetup.printArea='A1:K'+total;ws.headerFooter.oddFooter='&LPage &P of &N&REnd-Time Verification';
 return wb;
}
const api={HEADERS,data,csv,workbook};if(typeof module!=='undefined')module.exports=api;else root.VerificationExport=api;
})(typeof window==='undefined'?{}:window);
