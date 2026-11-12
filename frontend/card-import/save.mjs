export async function uploadSets(sets,bridge,progress) {
  if(!sets.length)throw Error('Select at least one card.');
  for(const set of sets){
    if(!set.front)throw Error('An unpaired back needs a front before saving.');
    for(const side of [set.front,set.back].filter(Boolean))if(!side.maskReviewed)throw Error('Review masking on every selected front and back before saving.');
    if(set.front.expiry_date&&set.front.issued_date&&set.front.expiry_date<set.front.issued_date)throw Error('Expiry must be on or after issue date.');
    if(set.front.saveUncertain)throw Error('A previous save response was lost. Close import and check the worker’s saved cards before importing this card again.');
  }
  for(const [index,set] of sets.entries()){
    const card=set.front;progress(`Saving ${index+1} of ${sets.length}…`);
    for(const [side,item] of [['front',card],['back',set.back]]){
      if(!item)continue;
      if(card.savedImages?.[side]===item.jpeg)continue;
      const bytes=Uint8Array.from(atob(item.jpeg.split(',')[1]),c=>c.charCodeAt(0));
      const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
      // Masks are already burned into pixels; server rebuilds this reviewed raster.
      const plan=JSON.stringify({policy:'fin-dob-wp-v1',sha256:hash,pages:[{reviewed:true,boxes:[]}]});
      try{card.savedRecord=await bridge.upload(side,bytes,plan,card.savedRecord);}
      catch(e){card.saveUncertain=true;throw Error(`${e.message} Save status is uncertain. Check saved cards before retrying.`);}
      card.savedImages??={};card.savedImages[side]=item.jpeg;
    }
    card.savedRecord=await bridge.details(card.savedRecord,{category:/work permit/i.test(card.title)?'work_permit':/visit pass/i.test(card.title)?'visit_pass':'course',label:card.title||'Card',institute:card.institute||null,cert_no:card.cert_no||null,issued_date:card.issued_date||null,expiry_date:card.no_expiry?null:card.expiry_date||null,no_expiry:!!card.no_expiry});
  }
  progress(`${sets.length} card sets saved. You can preview or download the A4 PDF.`);
}
