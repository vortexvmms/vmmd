/* Card text interpretation is shared by browser autofill and contract tests. */
(function(root){'use strict';
const normal=v=>String(v||'').toUpperCase().replace(/[^A-Z0-9]/g,'');
const unique=xs=>[...new Set(xs.filter(Boolean))];
const MONTHS=['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
function date(value){
  const s=String(value||'').trim();let y,m,d,a;
  if((a=s.match(/^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$/)))[,y,m,d]=a;
  else if((a=s.match(/^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$/)))[,d,m,y]=a;
  else if((a=s.match(/^(\d{1,2})[\s-]+([A-Za-z]+)[\s,-]+(\d{4})$/))){d=a[1];m=MONTHS.indexOf(a[2].slice(0,3).toUpperCase())+1;y=a[3]}
  else return '';
  if(+y<1900||+y>2200||+m<1||+m>12||+d<1)return '';
  const v=new Date(Date.UTC(+y,+m-1,+d));
  return v.getUTCFullYear()===+y&&v.getUTCMonth()===+m-1&&v.getUTCDate()===+d?v.toISOString().slice(0,10):'';
}
const DATE='(?:\\d{4}[-/.]\\d{1,2}[-/.]\\d{1,2}|\\d{1,2}[-/.]\\d{1,2}[-/.]\\d{4}|\\d{1,2}[\\s-]+[A-Za-z]{3,9}[\\s,-]+\\d{4})';
const labels={name:'(?:worker(?:[ \\t]+name)?|name(?:[ \\t]+of[ \\t]+(?:worker|participant))?|participant[ \\t]+name|card[ \\t]*holder)',site:'(?:site(?![ \\t]+induction)(?:[ \\t]+name)?|project(?:[ \\t]+name)?)',reference:'(?:(?:card|certificate|cert|reference)[ \\t]*(?:no\\.?|number|#|reference))',issuer:'(?:issued[ \\t]+by|issuer|training[ \\t]+provider)',sic_date:'(?:sic[ \\t]+date|(?:date[ \\t]+of[ \\t]+)?(?:site[ \\t]+)?induction(?:[ \\t]+date)?|course[ \\t]+date|issue[ \\t]+date|date[ \\t]+of[ \\t]+issue)',expiry_date:'(?:expiry(?:[ \\t]+date)?|expiration(?:[ \\t]+date)?|valid[ \\t]+(?:until|till|to)|date[ \\t]+of[ \\t]+expiry)'};
function labelled(text,label,pattern){
  const re=new RegExp('(?:^|\\n)[ \\t]*'+label+'[ \\t]*[:#-]?[ \\t]*(?:\\n[ \\t]*)?('+pattern+')','gim');
  return [...text.matchAll(re)].map(m=>m[1].trim());
}
function parse(text){
  text=String(text||'').replace(/\r/g,'').slice(0,100000);
  const fields={};
  fields.fin=unique([...text.toUpperCase().matchAll(/\b[STFGM]\d{7}[A-Z]\b/g)].map(m=>m[0]));
  for(const k of ['name','site','reference','issuer'])fields[k]=unique(labelled(text,labels[k],'[^\\n]+'));
  for(const k of ['sic_date','expiry_date'])fields[k]=unique(labelled(text,labels[k],DATE).map(date));
  fields.validity_months=unique(labelled(text,'(?:validity(?:[ \\t]+period)?|valid[ \\t]+for)','\\d{1,3}[ \\t]*(?:months?|years?)').map(v=>{const n=parseInt(v,10)*(/year/i.test(v)?12:1);return n>=1&&n<=120?n:null}));
  return fields;
}
function merge(parts){const keys=Object.keys(parse(''));return Object.fromEntries(keys.map(k=>[k,unique(parts.flatMap(p=>(p.fields||parse(p.text))[k]||[]))]))}
function matchWorker(fields,workers){
  const candidates=workers.filter(w=>['active','on_leave'].includes(w.status));
  if(fields.fin.length){if(fields.fin.length!==1)return null;const hits=candidates.filter(w=>normal(w.fin)===normal(fields.fin[0]));if(hits.length)return hits.length===1?hits[0]:null;if(fields.name.length!==1)return null;const named=candidates.filter(w=>normal(w.name)===normal(fields.name[0]));return named.length===1&&!named[0].fin?named[0]:null}
  if(fields.name.length!==1)return null;const hits=candidates.filter(w=>normal(w.name)===normal(fields.name[0]));return hits.length===1?hits[0]:null;
}
function matchSite(fields,sites,text=''){
  if(fields.site.length>1)return null;
  const candidates=fields.site.length?sites.filter(s=>normal(s.site_name)===normal(fields.site[0])):sites.filter(s=>{const n=normal(s.site_name);return n.length>=4&&String(text).split(/\n/).some(line=>normal(line)===n)});
  return candidates.length===1?candidates[0]:null;
}
function drafts(parts){
  const files=[...new Set(parts.map(p=>p.fileIndex))].map(fileIndex=>{const pages=parts.filter(p=>p.fileIndex===fileIndex);return {fileIndex,pages,fields:merge(pages)}});
  function identity(f){
    if(f.fields.fin.length===1)return 'fin:'+f.fields.fin[0];
    if(f.fields.fin.length||f.fields.name.length!==1)return '';
    const name=normal(f.fields.name[0]),fins=unique(files.filter(x=>x.fields.fin.length===1&&x.fields.name.length===1&&normal(x.fields.name[0])===name).map(x=>x.fields.fin[0]));
    return fins.length===1?'fin:'+fins[0]:'name:'+name;
  }
  const identities=unique(files.map(identity));
  const groups=new Map();
  for(const f of files){let key=identity(f);if(!key&&identities.length===1&&!f.fields.fin.length&&!f.fields.name.length)key=identities[0];key=key||'file:'+f.fileIndex;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(f)}
  return [...groups.values()].map(fs=>({fileIndexes:fs.map(f=>f.fileIndex),parts:fs.flatMap(f=>f.pages),fields:merge(fs.flatMap(f=>f.pages)),mixed:fs.some(f=>f.fields.fin.length>1||f.fields.name.length>1)}));
}
const api={normal,date,parse,merge,matchWorker,matchSite,drafts};
if(typeof module!=='undefined')module.exports=api;else root.SICCardData=api;
})(typeof window==='undefined'?{}:window);
