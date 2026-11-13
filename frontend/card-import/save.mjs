import {cardCategory, reviewSides} from './fields.mjs';

const imagePayloads=new WeakMap();
async function imagePayload(card) {
  const cached=imagePayloads.get(card);
  if(cached?.jpeg===card.jpeg)return cached;
  const bytes=Uint8Array.from(atob(card.jpeg.split(',')[1]),c=>c.charCodeAt(0));
  const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
  const plan=JSON.stringify({policy:'fin-dob-wp-v1',sha256:hash,pages:[{reviewed:true,boxes:[]}]});
  const payload={jpeg:card.jpeg,bytes,plan};
  imagePayloads.set(card,payload);
  return payload;
}

export async function uploadSets(sets,bridge,progress,{reviewed=false}={}) {
  if(!sets.length)throw Error('Select at least one card.');
  for(const set of sets){
    const card=set.front;
    if(!card)throw Error('An unpaired back needs a front before saving.');
    if(!reviewed&&reviewSides(set).some(side=>!side.maskReviewed))throw Error('Review the required sides and confirm the batch before saving.');
    if(cardCategory(card)!=='work_permit'&&card.expiry_date&&card.issued_date&&card.expiry_date<card.issued_date)
      throw Error('Card '+card.number+': expiry must be on or after issue date.');
  }
  await bridge.check?.();
  const failed=[];
  for(const [index,{front:card,back}] of sets.entries()){
    const label=card.title||'Card '+card.number;
    progress(`Saving ${index+1} of ${sets.length} · ${label}`);
    const start=performance.now();
    try{
      card.importId??=crypto.randomUUID();
      for(const [side,item] of [['front',card],['back',back]]){
        if(!item||card.savedImages?.[side]===item.jpeg)continue;
        const {jpeg,bytes,plan}=await imagePayload(item);
        const record=await bridge.upload(side,bytes,plan,card.savedRecord,card.importId);
        if(record.id!==card.importId)throw Error('Unexpected card reference. Refresh the worker register before retrying.');
        card.savedRecord=record;
        (card.savedImages??={})[side]=jpeg;
      }
      const category=cardCategory(card);
      const permit=category==='work_permit';
      const fields={category,label:label.slice(0,200),institute:card.institute?.slice(0,200)||null,cert_no:card.cert_no?.slice(0,200)||null,
        issued_date:permit?null:card.issued_date||null,expiry_date:permit||card.no_expiry?null:card.expiry_date||null,no_expiry:!permit&&!!card.no_expiry};
      const signature=JSON.stringify(fields);
      if(card.savedDetails!==signature){
        card.savedRecord=await bridge.details(card.savedRecord,fields);
        card.savedDetails=signature;
      }
      card.saveError='';
    }catch(error){
      card.saveError=error.message;
      failed.push(label+' (crop '+card.number+'): '+error.message);
    }finally{
      console.debug('Worker card save duration (ms)',Math.round(performance.now()-start));
    }
  }
  if(failed.length)throw Error(`${sets.length-failed.length} of ${sets.length} saved. Retry failed cards. ${failed.join(' | ')}`);
  progress(`${sets.length} card sets saved. You can preview or download the A4 PDF.`);
}
