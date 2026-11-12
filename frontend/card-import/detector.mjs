export const detection = {
  minWidth: .15, maxWidth: .70, minHeight: .08, maxHeight: .60,
  minArea: .02, maxArea: .45, minRatio: .45, maxRatio: 2.20,
  rectangularity: .70, duplicateIoU: .63, maxAnalysisSide: 1700,
};

export const area = ({w,h}) => w*h;
export function intersection(a,b) {
  return Math.max(0, Math.min(a.x+a.w,b.x+b.w)-Math.max(a.x,b.x)) *
    Math.max(0, Math.min(a.y+a.h,b.y+b.h)-Math.max(a.y,b.y));
}
export function iou(a,b) {
  const overlap = intersection(a,b);
  return overlap / (area(a)+area(b)-overlap);
}
export const encloses = (a,b) => intersection(a,b)/area(b) >= .92;

function hull(points) {
  const sorted = points.sort((a,b) => a.x-b.x || a.y-b.y);
  const cross = (a,b,c) => (b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);
  function half(list) {
    const result=[];
    for (const point of list) {
      while (result.length>1 && cross(result.at(-2),result.at(-1),point)<=0) result.pop();
      result.push(point);
    }
    return result.slice(0,-1);
  }
  return [...half(sorted),...half(sorted.reverse())];
}

function geometry(points) {
  if (points.length<3) return null;
  let best, enclosed=0;
  for (let i=0;i<points.length;i++) {
    const a=points[i], b=points[(i+1)%points.length];
    enclosed+=a.x*b.y-a.y*b.x;
    const angle=Math.atan2(b.y-a.y,b.x-a.x);
    const cos=Math.cos(angle), sin=Math.sin(angle);
    let u0=Infinity,v0=Infinity,u1=-Infinity,v1=-Infinity;
    for (const p of points) {
      const u=p.x*cos+p.y*sin,v=-p.x*sin+p.y*cos;
      u0=Math.min(u0,u); u1=Math.max(u1,u); v0=Math.min(v0,v); v1=Math.max(v1,v);
    }
    const size=(u1-u0+1)*(v1-v0+1);
    if (!best || size<best.size) best={size,angle};
  }
  const angle=((best.angle+Math.PI/4+Math.PI*2)%(Math.PI/2))-Math.PI/4;
  return {angle, rectangularity:Math.abs(enclosed)/(2*best.size)};
}

function contours(mask,w,h,sourceScaleX,sourceScaleY,sourceWidth,sourceHeight) {
  const queue=new Int32Array(mask.length), candidates=[];
  const left=new Int32Array(h),right=new Int32Array(h),visitedRow=new Int32Array(h);
  for (let start=0;start<mask.length;start++) {
    if (!mask[start]) continue;
    let head=0, tail=1, x0=w,x1=0,y0=h,y1=0;
    queue[0]=start;
    mask[start]=0;
    while (head<tail) {
      const i=queue[head++], x=i%w,y=(i-x)/w;
      x0=Math.min(x0,x); x1=Math.max(x1,x); y0=Math.min(y0,y); y1=Math.max(y1,y);
      if (visitedRow[y]!==start+1) { left[y]=x; right[y]=x; visitedRow[y]=start+1; }
      else { left[y]=Math.min(left[y],x); right[y]=Math.max(right[y],x); }
      for (let dy=-1;dy<=1;dy++) {
        if (y+dy<0 || y+dy>=h) continue;
        for (let dx=-1;dx<=1;dx++) {
          if (x+dx<0 || x+dx>=w) continue;
          const j=i+dy*w+dx;
          if (mask[j]) {mask[j]=0;queue[tail++]=j;}
        }
      }
    }
    const cw=x1-x0+1,ch=y1-y0+1, fraction=cw*ch/(w*h), ratio=cw/ch;
    if (cw<w*detection.minWidth*.86 || cw>w*detection.maxWidth*1.10 ||
        ch<h*detection.minHeight*.86 || ch>h*detection.maxHeight*1.10 ||
        fraction<detection.minArea*.82 || fraction>detection.maxArea*1.07 ||
        ratio<detection.minRatio*.87 || ratio>detection.maxRatio*1.12) continue;
    const points=[];
    for (let y=y0;y<=y1;y++) if (visitedRow[y]===start+1) points.push({x:left[y],y},{x:right[y],y});
    const outline=geometry(hull(points));
    if (!outline || outline.rectangularity<.58) continue;
    const padding=1.5;
    const x=Math.max(0,Math.floor((x0-padding)*sourceScaleX));
    const y=Math.max(0,Math.floor((y0-padding)*sourceScaleY));
    const r=Math.min(sourceWidth,Math.ceil((x1+1+padding)*sourceScaleX));
    const b=Math.min(sourceHeight,Math.ceil((y1+1+padding)*sourceScaleY));
    candidates.push({x,y,w:r-x,h:b-y, angle:outline.angle,
      confidence:Math.min(.98,outline.rectangularity*.94 + .05),
      incomplete:x0<=1 || y0<=1 || x1>=w-2 || y1>=h-2});
  }
  return candidates;
}

function closeMask(mask,w,h) {
  const expanded=new Uint8Array(mask.length), closed=new Uint8Array(mask.length);
  for (let y=0;y<h;y++) for (let x=0;x<w;x++) {
    const i=y*w+x;
    expanded[i]=mask[i] || (x>0 && mask[i-1]) || (x+1<w && mask[i+1]) ||
      (y>0 && mask[i-w]) || (y+1<h && mask[i+w]) ? 1 : 0;
  }
  for (let y=0;y<h;y++) for (let x=0;x<w;x++) {
    const i=y*w+x;
    closed[i]=expanded[i] && (!x || expanded[i-1]) && (x===w-1 || expanded[i+1]) &&
      (!y || expanded[i-w]) && (y===h-1 || expanded[i+w]) ? 1 : 0;
  }
  return closed;
}

export function detectCards(rgba,w,h,sourceWidth=w,sourceHeight=h) {
  const gray=new Uint8Array(w*h), blur=new Uint8Array(w*h), histogram=new Uint32Array(256);
  for (let i=0;i<gray.length;i++) {
    gray[i]=(rgba[i*4]*77+rgba[i*4+1]*150+rgba[i*4+2]*29)>>8;
    histogram[gray[i]]++;
  }
  let ceiling=255, highCount=histogram[255];
  while (ceiling>210 && highCount<gray.length*.12) highCount+=histogram[--ceiling];
  for (let i=0;i<gray.length;i++) gray[i]=Math.min(255,Math.round(gray[i]*255/ceiling));
  blur.set(gray);
  for (let y=1;y<h-1;y++) for (let x=1;x<w-1;x++) {
    const i=y*w+x;
    blur[i]=(gray[i]*4+gray[i-1]+gray[i+1]+gray[i-w]+gray[i+w])>>3;
  }
  const masks=Array.from({length:6},()=>new Uint8Array(gray.length));
  for (let y=0;y<h;y++) for (let x=0;x<w;x++) {
    const i=y*w+x;
    const gradient=Math.max(Math.abs(blur[i]-blur[y*w+Math.min(w-1,x+1)]),
      Math.abs(blur[i]-blur[Math.min(h-1,y+1)*w+x]));
    const local=(blur[y*w+Math.max(0,x-5)]+blur[y*w+Math.min(w-1,x+5)]+
      blur[Math.max(0,y-5)*w+x]+blur[Math.min(h-1,y+5)*w+x])/4;
    masks[0][i]=gradient>=20;
    masks[1][i]=gradient>=7;
    masks[2][i]=gray[i]<local-8;
    masks[3][i]=gray[i]<242;
    const r=rgba[i*4],g=rgba[i*4+1],b=rgba[i*4+2];
    masks[4][i]=Math.max(r,g,b)-Math.min(r,g,b)>=11 && gray[i]<247;
    masks[5][i]=gray[i]<226;
  }
  const pool=masks.flatMap((mask,index)=>contours(index<3 || index>=4 ? closeMask(mask,w,h) : mask,
    w,h,sourceWidth/w,sourceHeight/h,sourceWidth,sourceHeight));
  const unique=[];
  for (const candidate of pool.sort((a,b)=>b.confidence-a.confidence || area(b)-area(a))) {
    if (!unique.some(other=>iou(candidate,other)>detection.duplicateIoU)) unique.push(candidate);
  }
  const groups=unique.filter(box=>{
    const children=unique.filter(child=>child!==box && child.confidence>=detection.rectangularity &&
      area(child)<area(box)*.79 && encloses(box,child));
    return children.some((a,i)=>children.slice(i+1).some(b=>iou(a,b)<.12 &&
      (area(a)+area(b))/area(box)>.46 && Math.min(area(a),area(b))>area(box)*.16));
  });
  const accepted=unique.filter(box=>{
    const nearLeft=box.x<sourceWidth*.019, nearRight=box.x+box.w>sourceWidth*.981;
    const scannerBand=(nearLeft || nearRight) && unique.some(other=>other!==box &&
      other.x>box.x+sourceWidth*.07 && other.x+other.w<=box.x+box.w+sourceWidth*.03 &&
      other.h/box.h>.83 && other.w/box.w<.77 && intersection(box,other)/area(other)>.82);
    return !scannerBand && !groups.includes(box);
  });
  const outer=accepted.filter(box=>!accepted.some(other=>other!==box && area(other)>area(box)*1.15 &&
    other.confidence>=box.confidence-.15 && encloses(other,box)));
  outer.sort((a,b)=>a.y-b.y || a.x-b.x);
  const rows=[];
  for (const box of outer) {
    const row=rows.find(r=>Math.abs(r[0].y-box.y)<Math.min(r[0].h,box.h)*.24);
    if (row) row.push(box); else rows.push([box]);
  }
  return rows.flatMap(row=>row.sort((a,b)=>a.x-b.x));
}

export function withMargin(box,neighbors,width,height,margin) {
  const sides={left:Math.min(margin,box.x),top:Math.min(margin,box.y),
    right:Math.min(margin,width-box.x-box.w),bottom:Math.min(margin,height-box.y-box.h)};
  for (const other of neighbors) {
    if (iou(box,other)>.70) continue;
    const vertical=other.y<box.y+box.h+margin && other.y+other.h>box.y-margin;
    const horizontal=other.x<box.x+box.w+margin && other.x+other.w>box.x-margin;
    if (vertical && other.x+other.w<=box.x) sides.left=Math.min(sides.left,Math.max(0,box.x-other.x-other.w-1));
    if (vertical && other.x>=box.x+box.w) sides.right=Math.min(sides.right,Math.max(0,other.x-box.x-box.w-1));
    if (horizontal && other.y+other.h<=box.y) sides.top=Math.min(sides.top,Math.max(0,box.y-other.y-other.h-1));
    if (horizontal && other.y>=box.y+box.h) sides.bottom=Math.min(sides.bottom,Math.max(0,other.y-box.y-box.h-1));
  }
  return {x:box.x-sides.left,y:box.y-sides.top,w:box.w+sides.left+sides.right,h:box.h+sides.top+sides.bottom};
}
