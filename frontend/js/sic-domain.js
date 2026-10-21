/* Pure SIC date/filter rules, shared by the page and regression tests. */
(function(root){'use strict';
const iso=d=>d.toISOString().slice(0,10);
function expiry(date,months){if(!date||!Number.isInteger(+months)||+months<1||+months>120)return '';const [y,m,d]=date.split('-').map(Number);const start=new Date(Date.UTC(y,m-1,d));if(iso(start)!==date)return '';const first=new Date(Date.UTC(y,m-1+(+months),1));first.setUTCDate(Math.min(d,new Date(Date.UTC(first.getUTCFullYear(),first.getUTCMonth()+1,0)).getUTCDate()));first.setUTCDate(first.getUTCDate()-1);return iso(first)}
function today(){return new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Singapore',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())}
function days(date,now=today()){return Math.round((Date.parse(date+'T00:00:00Z')-Date.parse(now+'T00:00:00Z'))/86400000)}
function status(date,now=today()){const n=days(date,now);return n<0?'Expired':n<=30?'Expiring Soon':'Valid'}
function dashboardSelection(filters,view='urgent',now=today()){
  const result={...filters};
  const offset=n=>iso(new Date(Date.parse(now+'T00:00:00Z')+n*86400000));
  if(view==='valid')result.status='Valid';
  else if(view==='expired')result.status='Expired';
  else if(['urgent','7','30','60'].includes(view)){
    const end=offset(view==='urgent'?30:Number(view));
    result.expiryTo=result.expiryTo&&result.expiryTo<end?result.expiryTo:end;
    if(view!=='urgent')result.expiryFrom=result.expiryFrom&&result.expiryFrom>now?result.expiryFrom:now;
  }
  return result;
}
function dashboardSummary(rows,now=today()){
  const counts={workers:new Set(rows.map(r=>r.worker_id)).size,records:rows.length,valid:0,soon:0,expired:0},groups=new Map();
  for(const r of rows){const key=status(r.expiry_date,now)==='Expired'?'expired':status(r.expiry_date,now)==='Expiring Soon'?'soon':'valid';counts[key]++;if(!groups.has(r.site_id))groups.set(r.site_id,{id:r.site_id,name:r.site_name,total:0,valid:0,soon:0,expired:0});const group=groups.get(r.site_id);group.total++;group[key]++}
  return {counts,sites:[...groups.values()].sort((a,b)=>b.expired-a.expired||b.soon-a.soon||a.name.localeCompare(b.name))};
}
function filter(rows,f,now=today()){return rows.filter(r=>(!f.q||[r.name,r.fin,r.site_name].join(' ').toLowerCase().includes(f.q.toLowerCase()))&&(!f.site||r.site_id===f.site)&&(!f.status||status(r.expiry_date,now)===f.status)&&(!f.card||(f.card==='missing'?!r.card_count:r.card_count>0))&&(!f.worker||f.worker==='all'||(f.worker==='active'?['active','on_leave'].includes(r.worker_status):!['active','on_leave'].includes(r.worker_status)))&&(!f.archive||f.archive==='all'||(f.archive==='archived'?r.archived:!r.archived))&&(!f.sicFrom||r.sic_date>=f.sicFrom)&&(!f.sicTo||r.sic_date<=f.sicTo)&&(!f.expiryFrom||r.expiry_date>=f.expiryFrom)&&(!f.expiryTo||r.expiry_date<=f.expiryTo)).sort((a,b)=>(f.sort==='created_at'?String(b.created_at).localeCompare(String(a.created_at)):String(a[f.sort||'name']).localeCompare(String(b[f.sort||'name'])))||a.id.localeCompare(b.id))}
function siteChoices(sites,records=[]){const name=s=>String(s.site_name||'').trim().replace(/\s+/g,' ').toLowerCase();return sites.filter(s=>(!s.removed_at||records.some(r=>r.site_id===s.id))&&(s.status!=='archived'||!sites.some(a=>a.status==='active'&&name(a)===name(s))||records.some(r=>r.site_id===s.id)))}
function excelText(v){return String(v??'').replace(/^[=+\-@\t\r]/,"'$&")}
const api={expiry,today,days,status,dashboardSelection,dashboardSummary,filter,siteChoices,excelText};if(typeof module!=='undefined')module.exports=api;else root.SIC=api;
})(typeof window==='undefined'?{}:window);
