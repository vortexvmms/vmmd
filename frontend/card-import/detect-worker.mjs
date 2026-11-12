import {detectCards} from './detector.mjs';

self.onmessage = ({data}) => {
  const {pixels,width,height,sourceWidth,sourceHeight}=data;
  self.postMessage(detectCards(pixels,width,height,sourceWidth,sourceHeight));
};
