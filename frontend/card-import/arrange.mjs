export function scanIdentity(filename) {
  let name=filename.replace(/\.pdf$/i,'').replace(/^\s*\d+[.\-_) ]+\s*/,'').trim();
  const suffix=name.match(/\s*[-–_]\s*([A-Z]?\d{3,}[A-Z]?)$/i);
  if (suffix) name=name.slice(0,suffix.index).trim();
  return {name:name.toUpperCase(),fin:suffix?.[1].slice(-4).toUpperCase() || ''};
}

export function matchScannedSides(cards,mode,pageCount) {
  if (mode==='allfront') return;
  const offset=mode==='pairs'?1:Math.ceil(pageCount/2);
  const candidates=cards.filter(card=>card.position && !card.partner && !card.pairOverride &&
    !['Duplicate','Multiple Cards','Mostly Blank'].includes(card.status));
  const score=(a,b)=>{
    const p=a.position,q=b.position;
    const dx=Math.abs(p.x-q.x),dy=Math.abs(p.y-q.y);
    const size=Math.max(Math.abs(Math.log(p.w/q.w)),Math.abs(Math.log(p.h/q.h)));
    if (dx>Math.min(.09,Math.min(p.w,q.w)*.35) || dy>Math.min(.09,Math.min(p.h,q.h)*.35) || size>.48) return Infinity;
    return Math.hypot(dx,dy)+size*.04;
  };
  const nearest=(card,others)=>{
    const ranked=others.map(other=>({other,score:score(card,other)}))
      .filter(item=>Number.isFinite(item.score)).sort((a,b)=>a.score-b.score);
    return ranked[0] && (!ranked[1] || ranked[1].score-ranked[0].score>.014) ? ranked[0].other : null;
  };
  for (const front of candidates.filter(card=>card.side==='Front' && (mode!=='pairs' || card.page%2))) {
    const backs=candidates.filter(card=>card.side==='Back' && card.page===front.page+offset);
    const back=nearest(front,backs);
    if (!back || back.partner || nearest(back,candidates.filter(card=>card.side==='Front' && card.page===front.page))!==front) continue;
    front.partner=back.id; back.partner=front.id;
  }
}

export function selectedSets(cards) {
  const byId=new Map(cards.map(card=>[card.id,card]));
  return cards.filter(card=>card.side==='Front' || !byId.has(card.partner)).map(card=>({
    id:card.id, front:card.side==='Front'?card:null,
    back:card.side==='Back'?card:byId.get(card.partner) || null,
  }));
}

const pt=mm=>mm*72/25.4;
const pageWidth=pt(210), pageHeight=pt(297);
const margin=pt(10), columnGap=pt(4), rowGap=pt(2), headerHeight=22;
const columnWidth=(pageWidth-margin*2-columnGap)/2;
function cardRows(sets) {
  const rows=sets.map(set=>{
    const cards=[set.front,set.back].map(card=>{
      if (!card) return null;
      const [width,height]=card.size.split(' × ').map(Number);
      if (!(Number.isFinite(width) && Number.isFinite(height) && width>0 && height>0)) {
        throw new Error('A card image is missing its dimensions.');
      }
      return {jpeg:card.jpeg,width,height};
    });
    const fullWidthHeight=Math.max(...cards.filter(Boolean).map(card=>columnWidth*card.height/card.width));
    return {cards,fullWidthHeight,height:0};
  });
  let remaining=pageHeight-margin*2-headerHeight-rowGap*(rows.length-1);
  // Give space a landscape row cannot use to the taller rows on this page.
  for (const [index,row] of [...rows].sort((a,b)=>a.fullWidthHeight-b.fullWidthHeight).entries()) {
    row.height=Math.min(row.fullWidthHeight,remaining/(rows.length-index));
    remaining-=row.height;
  }
  return rows;
}
const encoder=new TextEncoder();
const number=value=>value.toFixed(3);
const jpegBytes=uri=>Uint8Array.from(atob(uri.slice(uri.indexOf(',')+1)),char=>char.charCodeAt(0));

export function makeCardPdf(sets,header) {
  if (!sets.length) throw new Error('Select at least one card set.');
  const objects=[null,null];
  const add=(...chunks)=>objects.push(chunks);
  const image=({jpeg,width,height})=>{
    const bytes=jpegBytes(jpeg);
    return add(`<< /Type /XObject /Subtype /Image /Width ${width} /Height ${height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${bytes.length} >>\nstream\n`,bytes,'\nendstream');
  };
  const headerId=image(header), pageIds=[];
  for (let start=0;start<sets.length;start+=4) {
    const resources=[`/Heading ${headerId} 0 R`];
    const headerWidth=Math.min(pageWidth-margin*2,18*header.width/header.height);
    const commands=[`q ${number(headerWidth)} 0 0 18 ${number(margin)} ${number(pageHeight-margin-18)} cm /Heading Do Q\n`];
    let rowTop=pageHeight-margin-headerHeight;
    for (const [row,{cards,height:rowHeight}] of cardRows(sets.slice(start,start+4)).entries()) {
      for (const [column,card] of cards.entries()) {
        if (!card) continue;
        const label=`Card${row}${column}`;
        resources.push(`/${label} ${image(card)} 0 R`);
        const scale=Math.min(columnWidth/card.width,rowHeight/card.height);
        const w=card.width*scale,h=card.height*scale;
        const x=margin+column*(columnWidth+columnGap);
        const y=rowTop-h;
        commands.push(`q ${number(w)} 0 0 ${number(h)} ${number(x)} ${number(y)} cm /${label} Do Q\n`);
      }
      rowTop-=rowHeight+rowGap;
    }
    const content=commands.join('');
    const stream=add(`<< /Length ${encoder.encode(content).length} >>\nstream\n${content}endstream`);
    pageIds.push(add(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${number(pageWidth)} ${number(pageHeight)}] /Resources << /XObject << ${resources.join(' ')} >> >> /Contents ${stream} 0 R >>`));
  }
  objects[0]=['<< /Type /Catalog /Pages 2 0 R >>'];
  objects[1]=[`<< /Type /Pages /Count ${pageIds.length} /Kids [${pageIds.map(id=>id+' 0 R').join(' ')}] >>`];
  const parts=[];
  let position=0;
  function append(chunk) {
    const bytes=typeof chunk==='string'?encoder.encode(chunk):chunk;
    parts.push(bytes); position+=bytes.length;
  }
  append('%PDF-1.4\n');
  append(Uint8Array.of(37,226,227,207,211,10));
  const offsets=objects.map((chunks,index)=>{
    const offset=position;
    append(`${index+1} 0 obj\n`);
    for (const chunk of chunks) append(chunk);
    append('\nendobj\n');
    return offset;
  });
  const xref=position;
  append(`xref\n0 ${objects.length+1}\n0000000000 65535 f \n`);
  for (const offset of offsets) append(`${String(offset).padStart(10,'0')} 00000 n \n`);
  append(`trailer\n<< /Size ${objects.length+1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
  return new Blob(parts,{type:'application/pdf'});
}
