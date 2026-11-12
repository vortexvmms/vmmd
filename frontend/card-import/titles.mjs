const topic=/\b(course|training|induction|permit|certificate|safety|pass|competency|orientation|fire watch|chemical[s]? complex|operator|supervisor|work at height|workplace|rigg(?:er|ing)|signalman|scaffold(?:er|ing)|lifting|forklift|terminal|petrochemical)\b/i;
const field=/^(name|date|expiry|valid until|fin|nric|id no|issued|signature|employer|company|card no|pass no|attended on|republic of)\b/i;

export function suggestedTitle(lines) {
  const rows=lines.map(line=>(typeof line==='string'?{text:line}:line))
    .map(line=>({...line,text:line.text.replace(/\s+/g,' ').trim()}))
    .filter(line=>line.text.length>=3 && line.text.length<=105 && /[a-z]{3}/i.test(line.text) &&
      !field.test(line.text) && !/\b\d{4,}\b/.test(line.text))
    .sort((a,b)=>(a.y??0)-(b.y??0) || (a.x??0)-(b.x??0));
  const heading=rows.filter(line=>(line.y??0)<.49);
  const flat=heading.map(line=>line.text).join(' ');
  if (/\bS\s*[- ]?\s*PASS\b/.test(flat)) return 'S Pass';
  if (/\bADV[^a-z]{0,2}[a-z]?RIO\b/i.test(flat) && /\bsafety induction course\b/i.test(flat)) return 'Advario Safety Induction Course';
  if (/\bsingapore\s+petrochemical\b/i.test(flat)) return 'Singapore Petrochemical Complex';
  const course=heading.find(line=>/\bcourse title\s*:/i.test(line.text));
  if (course) {
    const title=course.text.replace(/^.*?\bcourse title\s*:\s*/i,'');
    const continued=heading.filter(line=>line!==course &&
      Math.abs((line.y??0)-(course.y??0))<Math.max(course.height??.04,line.height??.04)*1.65 &&
      !/^(~|also known|known as|cs code|serial|services|id no)/i.test(line.text) &&
      ((line.y??0)>(course.y??0)+.015 || (line.x??0)>(course.x??0)+.18));
    const next=continued[0]?.text || '';
    if (title.length>=8) return [title,next].filter(Boolean).join(' ').replace(/\s+and$/i,'');
    if (next.length>=8) return next;
  }
  if (/\bwork\s+permit\b/i.test(flat) && !/permit\s+to\s+work/i.test(flat)) return 'Work Permit';
  if (/\bfire\s+watch\s+record\b/i.test(flat)) return 'Fire Watch Record';
  if (/\bsingapore\s+essential\s+chemical[s]?\s+complex\b/i.test(flat)) return 'Singapore Essential Chemicals Complex';

  const options=[];
  for (const [i,line] of heading.entries()) {
    let text=line.text;
    if (/^course title\s*:?$/i.test(text)) continue;
    const next=heading[i+1];
    if (next && line.height && next.height && !field.test(next.text) &&
        next.y-line.y<Math.max(line.height,next.height)*2 &&
        next.height/line.height>.7 && next.height/line.height<1.45 &&
        Math.abs(next.x-line.x)<.24 && text.length+next.text.length<100 &&
        (!topic.test(text) || /\b(safety|training|induction|competency|fire watch|and)$/i.test(text) || /^(WORK|TASKS|OPERATIONS)$/i.test(next.text)) &&
        !/^(the|this|for|attended|conducted|valid|issued)\b/i.test(next.text)) text+=' '+next.text;
    if (topic.test(text)) options.push({text,score:(line.height??.035)*4-(line.y??0)*.4+Math.min(text.length,48)/400});
  }
  return options.sort((a,b)=>b.score-a.score)[0]?.text || '';
}

export function recognizedFin(lines) {
  for (const {text} of lines) {
    const fin=text.match(/\bFIN(?:\s*(?:NO\.?|NUMBER))?\s*[:#-]?\s*([FGM]\d{7}[A-Z])\b/i);
    if (fin) return fin[1].slice(-4).toUpperCase();
  }
  return '';
}
