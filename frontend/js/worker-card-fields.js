/* Conservative suggestions from the selected card's OCR text. */
(function(root){
'use strict';
const months='jan feb mar apr may jun jul aug sep oct nov dec'.split(' ');
const expiryLabel=/\b(?:expir(?:y|es|ation|e)(?:\s+date)?|valid\s+(?:till|until|to|through)|date\s+of\s+expiry)\b/i;
const fieldBoundary=/\b(?:date of birth|issued? date|date of issue|valid from|certificate (?:no|number)|course (?:name|title)|training provider)\b/i;

function expiry(text){
 const label=text.match(expiryLabel);
 if(!label)return '';
 const value=text.slice(label.index+label[0].length).replace(/^[\s:–-]+/,'').split(fieldBoundary)[0].trim();
 const numeric=value.match(/^(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{4}|\d{2})\b/);
 const named=value.match(/^(\d{1,2})[\s/.\-]+([a-z]{3,9})[\s,/.\-]+(\d{4}|\d{2})\b/i);
 const iso=value.match(/^(\d{4})\s*-\s*(\d{1,2})\s*-\s*(\d{1,2})\b/);
 if(!numeric&&!named&&!iso)return '';
 const [day,month,year]=iso?[iso[3],iso[2],iso[1]]:numeric?numeric.slice(1):[named[1],String(months.indexOf(named[2].slice(0,3).toLowerCase())+1),named[3]];
 const date=(year.length===2?'20'+year:year)+'-'+month.padStart(2,'0')+'-'+day.padStart(2,'0');
 const parsed=new Date(date+'T00:00:00Z');
 return Number.isFinite(parsed.valueOf())&&parsed.toISOString().slice(0,10)===date?date:'';
}

function labelled(lines,label){
 for(const [index,line] of lines.entries()){
  const match=line.match(label);
  if(!match)continue;
  const value=(match[1]||lines[index+1]||'').split(fieldBoundary)[0].split(expiryLabel)[0].trim();
  if(value.length>=3&&!expiryLabel.test(value)&&!fieldBoundary.test(value))return value;
 }
 return '';
}

function read(sides){
 const pages=sides.map(side=>side.split(/\r?\n/).map(line=>line.replace(/\s+/g,' ').trim()).filter(Boolean));
 const lines=pages.flat();
 const courseLabel=/^(?:(?:course|programme|qualification)\s*(?:name|title)\s*[:–-]?|(?:course|qualification)\s*[:–-])\s*(.*)$/i;
 const instituteLabel=/^(?:institute(?: name)?|training provider|training organisation|issued by)(?:\s*[:–-]\s*|\s+|$)(.*)$/i;
 const title=/\b(?:safety induction course|apply workplace safety|work at height|rigger (?:and|&) signalman|lifting supervisor|operate forklift|confined space)\b/i;
 const institutes=/\b(?:academy|institute|polytechnic|training cent(?:re|er)|(?:pte|private)\.?\s+ltd)\b/i;
 const front=pages[0]||[];
 const titleIndex=front.findIndex(line=>title.test(line)&&!fieldBoundary.test(line));
 const brand=front[titleIndex-1];
 const provider=brand&&/^(?:advario|shell|pcs|petrochemical corporation of singapore)\b/i.test(brand)?brand:'';
 const dates=new Set();
 for(const page of pages){
  for(const [index,line] of page.entries()){
   const value=expiry(line+' '+(page[index+1]||''));
   if(value)dates.add(value);
  }
 }
 return {
  label:labelled(lines,courseLabel)||(titleIndex>=0?front[titleIndex]:''),
  institute:labelled(lines,instituteLabel)||provider||front.find(line=>institutes.test(line)&&!title.test(line)&&!fieldBoundary.test(line))||'',
  expiry_date:dates.size===1?[...dates][0]:''
 };
}
root.WorkerCardFields={read};
})(typeof window==='undefined'?globalThis:window);
