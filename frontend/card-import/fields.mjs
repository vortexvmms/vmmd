const months='jan feb mar apr may jun jul aug sep oct nov dec'.split(' ');
const datePattern=/\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[ /.-]+(?:[a-z]{3,9}|\d{1,2})[ /.,-]+\d{4})\b/i;
export function parseCardDate(text) {
  const match=text.match(datePattern);
  if(!match)return '';
  let [day,month,year]=match[0].split(/[ /.,-]+/);
  if(day.length===4)[year,month,day]=[day,month,year];
  else if(/^\d+$/.test(month)&&Number(day)<=12&&Number(month)<=12&&day!==month)return '';
  if(/[a-z]/i.test(month))month=String(months.indexOf(month.slice(0,3).toLowerCase())+1);
  const iso=year+'-'+month.padStart(2,'0')+'-'+day.padStart(2,'0');
  const date=new Date(iso+'T00:00:00Z');
  return Number.isFinite(+date)&&date.toISOString().slice(0,10)===iso?iso:'';
}
export function calculatedExpiry(issue,period) {
  if(!issue||!period)return '';
  const [year,month,day]=issue.split('-').map(Number);
  const target=new Date(Date.UTC(year,month-1+period.months,1));
  const end=new Date(Date.UTC(target.getUTCFullYear(),target.getUTCMonth()+1,0)).getUTCDate();
  target.setUTCDate(Math.min(day,end)+period.days);
  return target.toISOString().slice(0,10);
}
const labels={
  title:/^\s*(?:course\s+(?:title|name)|training\s+(?:course|programme|program)|name of course)\s*[:–-]?\s*(.*)$/i,
  institute:/^\s*(?:institute(?:\s+name)?|training\s+(?:provider|institute|cent(?:re|er))|conducted by|issued by|awarded by)\s*[:–-]?\s*(.*)$/i,
  issued_date:/^\s*(?:date of issue|issue date|issued (?:on|date|dawe)|date issued)\s*[:–-]?\s*(.*)$/i,
  expiry_date:/^\s*(?:date of expiry|expir(?:y|ation)(?: date)?|expires(?: on)?|valid until)\s*[:–-]?\s*(.*)$/i
};
const boundary=/^(?:name|worker|employer|company|cert(?:ificate)?\s*(?:no|number)|fin|nric|id|training date|assessment|completion|serial number|cs code|validity|valid for|signature|date of birth)\b/i;
const providerHeading=/^[A-Z0-9 &.,'()-]{2,65}\b(?:ACADEMY|INSTITUTE|TRAINING(?: SERVICES)?|TRAINING CENT(?:RE|ER)|POLYTECHNIC)(?:\s+(?:PTE|PRIVATE|LTD|LIMITED)\.?){0,3}$/i;
const providerContinuation=/^(?:SERVICES\s+)?(?:PTE|PRIVATE|LTD|LIMITED)(?:\s+(?:PTE|PRIVATE|LTD|LIMITED))*\.?$/i;
const generic=/^(?:certificate(?: of (?:completion|attendance|achievement|training|competency))?|course card|training card|statement of attainment|certificate number|work permit)$/i;
const duration=/\b(\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten)\s*(years?|months?|days?)\s*(?:validity\s*)?(?:from|after)\s*(?:the\s+)?(?:date of issue|issue date|issuance)\b/i;
const words=['zero','one','two','three','four','five','six','seven','eight','nine','ten'];

export function readCourseFields(front,back=[]) {
  const candidates={title:[],institute:[],issued_date:[],expiry_date:[],period:[]};
  for(const [side,input] of [['Front',front],['Back',back]]){
    const lines=input.map(line=>typeof line==='string'?{text:line}:line).map(line=>({...line,text:line.text.trim()})).filter(line=>line.text);
    const explicitProvider=lines.some(line=>labels.institute.test(line.text));
    for(const [index,line] of lines.entries()){
      const text=line.text;
      if(!explicitProvider&&!boundary.test(text)&&providerHeading.test(text)&&(line.y==null||line.y<.55)){
        const suffix=lines.slice(index+1,index+4).find(next=>providerContinuation.test(next.text)&&
          (line.y==null||next.y==null||next.y-line.y<(line.height||.05)*5));
        const value=[text,suffix?.text].filter(Boolean).join(' ');
        candidates.institute.push({value,side,text:value,suggested:true});
      }
      const validity=text.match(duration)||lines.slice(index,index+2).map(r=>r.text).join(' ').match(duration);
      if(validity){
        const amount=Number(validity[1])||words.indexOf(validity[1].toLowerCase());
        if(amount>0)candidates.period.push({value:{months:/year/i.test(validity[2])?amount*12:/month/i.test(validity[2])?amount:0,days:/day/i.test(validity[2])?amount:0},side,text:validity[0]});
      }
      for(const [key,pattern] of Object.entries(labels)){
        const match=text.match(pattern);
        if(!match)continue;
        let value=match[1].replace(/^[.:=\s]+/u,'').trim();
        const sources=[text];
        for(const next of lines.slice(index+1,index+(key==='title'?4:2))){
          if(boundary.test(next.text)||Object.values(labels).some(re=>re.test(next.text))||duration.test(next.text)||generic.test(next.text))break;
          if(value&&key!=='title')break;
          if(value&&line.y!=null&&next.y!=null&&next.y-line.y>(line.height||.04)*4)break;
          if(value&&key==='title'&&!/^[A-Z0-9 (&/,-]+$/.test(next.text))break;
          value=[value,next.text].filter(Boolean).join(key==='title'?'\n':' ');
          sources.push(next.text);
        }
        if(key.endsWith('_date'))value=parseCardDate(value);
        else if(generic.test(value)||boundary.test(value))value='';
        candidates[key].push({value,side,text:sources.join(' / ')});
      }
    }
  }
  const fields={};
  for(const [key,items] of Object.entries(candidates)){
    const unique=new Set(items.filter(x=>x.value).map(x=>typeof x.value==='string'?x.value.toLowerCase().replace(/\s+/g,' '):JSON.stringify(x.value)));
    fields[key]={value:unique.size===1?items.find(x=>x.value).value:'',sources:items,
      review:unique.size!==1||items.some(x=>!x.value||x.suggested)};
  }
  return fields;
}

export function applyCourseFields(card,fields) {
  card.ocrFields=fields;
  for(const key of ['title','institute','issued_date','expiry_date']){
    if(card.editedFields?.[key]||key==='title'&&card.titleEdited)continue;
    card[key]=fields[key]?.value||'';
  }
  updateCalculatedExpiry(card);
}
export function updateCalculatedExpiry(card) {
  if(card.editedFields?.expiry_date||card.no_expiry)return;
  const {expiry_date:expiry,period}=card.ocrFields||{};
  if(!expiry)return;
  card.expiry_date=expiry.value||(!expiry.sources.length&&period.value?calculatedExpiry(card.issued_date,period.value):'');
}
export function cardCategory(card) {
  return card.category||(/\bwork\s+permit\b/i.test(card.title)?'work_permit':/\bvisit\s+pass\b/i.test(card.title)?'visit_pass':'course');
}
export function reviewSides(set) {
  return [set.front,cardCategory(set.front||{})==='work_permit'?set.back:null].filter(Boolean);
}
export function workerPdfName(name) {
  const safe=String(name||'').normalize('NFKC').replace(/[<>:"/\\|?*\x00-\x1f\x7f]/g,' ').trim().replace(/[\s.]+/g,'_').replace(/^_+|_+$/g,'').slice(0,110).toUpperCase();
  return (safe||'WORKER')+'_Worker_Cards.pdf';
}
