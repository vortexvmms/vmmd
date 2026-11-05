/* Conservative scan segmentation on a white scanner background. All processing is local. */
(function(root){'use strict';
function detect(source){
 const scale=Math.min(1,720/Math.max(source.width,source.height)),c=document.createElement('canvas');c.width=Math.round(source.width*scale);c.height=Math.round(source.height*scale);
 const w=c.width,h=c.height,x=c.getContext('2d');x.drawImage(source,0,0,w,h);const d=x.getImageData(0,0,w,h).data,ink=new Uint8Array(w*h),mask=new Uint8Array(w*h),seen=new Uint8Array(w*h);
 for(let i=0;i<ink.length;i++){const a=i*4,r=d[a],g=d[a+1],b=d[a+2];ink[i]=Math.min(r,g,b)<165||Math.max(r,g,b)-Math.min(r,g,b)>45?1:0;}
 // Join text and borders within a card without relying on front/back coordinates.
 const radius=4,integral=new Int32Array((w+1)*(h+1));
 for(let y=0;y<h;y++){let sum=0;for(let xx=0;xx<w;xx++){sum+=ink[y*w+xx];integral[(y+1)*(w+1)+xx+1]=integral[y*(w+1)+xx+1]+sum;}}
 for(let y=0;y<h;y++)for(let xx=0;xx<w;xx++){const l=Math.max(0,xx-radius),r=Math.min(w,xx+radius+1),t=Math.max(0,y-radius),b=Math.min(h,y+radius+1);mask[y*w+xx]=integral[b*(w+1)+r]-integral[t*(w+1)+r]-integral[b*(w+1)+l]+integral[t*(w+1)+l]>0?1:0;}
 const queue=new Int32Array(w*h),boxes=[];
 for(let start=0;start<mask.length;start++){if(!mask[start]||seen[start])continue;let read=0,n=1,l=w,r=0,t=h,b=0;queue[0]=start;seen[start]=1;
 while(read<n){const i=queue[read++],xx=i%w,y=Math.floor(i/w);l=Math.min(l,xx);r=Math.max(r,xx);t=Math.min(t,y);b=Math.max(b,y);for(const j of [xx?i-1:-1,xx+1<w?i+1:-1,y?i-w:-1,y+1<h?i+w:-1])if(j>=0&&mask[j]&&!seen[j]){seen[j]=1;queue[n++]=j;}}
 const bw=r-l+1,bh=b-t+1;if(bw<w*.085||bh<h*.045||bw*bh<w*h*.006||bw*bh>w*h*.85||n/(bw*bh)<.06)continue;
 const pad=6;boxes.push({x:Math.max(0,l-pad)/w,y:Math.max(0,t-pad)/h,w:(Math.min(w,r+pad+1)-Math.max(0,l-pad))/w,h:(Math.min(h,b+pad+1)-Math.max(0,t-pad))/h});}
 // Absorb fragments which are enclosed by another detected card boundary.
 return boxes.filter((a,i)=>!boxes.some((b,j)=>j!==i&&a.x>=b.x&&a.y>=b.y&&a.x+a.w<=b.x+b.w&&a.y+a.h<=b.y+b.h)).sort((a,b)=>Math.abs(a.y-b.y)>.055?a.y-b.y:a.x-b.x);
}
root.WorkerCardScanDetect={detect};
})(window);
