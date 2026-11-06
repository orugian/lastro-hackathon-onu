const { chromium } = require('../../tests/web/node_modules/playwright');
const fs = require('fs');
const path = require('path');
const {pathToFileURL} = require('url');
(async()=>{
 const out=path.join(__dirname,'references-'+Date.now());fs.mkdirSync(out);
 const browser=await chromium.launch({headless:true,channel:'msedge'});
 const page=await browser.newPage({viewport:{width:1440,height:810},deviceScaleFactor:1});
 const refs=[['3c',String.raw`C:\Users\orugi\.dsh\attachments\v1\files\d1\d1963cca9bd1722da96e04938dc762d882bf98d6c928ed49c4b2bfadc3e04925\apresentacao_3c_conecta (2) (1).html`],['newai',String.raw`C:\Users\orugi\.dsh\attachments\v1\files\d4\d41ee3d9f39609975c7533a13475f393c492003f5921c5e3552bf2683ceb2462\apresentacao-newai.html`]];
 for(const [name,file] of refs){
  await page.goto(pathToFileURL(file).href);await page.evaluate(()=>document.fonts.ready);
  const contents=await page.locator('section.slide').evaluateAll(ss=>ss.map(s=>({title:s.dataset.title,notes:s.dataset.notes,reserve:s.dataset.res||false,text:s.innerText})));
  fs.writeFileSync(path.join(out,name+'-structure.json'),JSON.stringify(contents,null,2));
  for (const idx of [0,2,3,5]){
   await page.locator('section.slide').evaluateAll((ss,ix)=>{ss.forEach(s=>s.classList.remove('on'));ss[ix].classList.add('on','static');ss[ix].querySelectorAll('[data-step]').forEach(e=>e.classList.remove('pending'));},idx);
   await page.screenshot({path:path.join(out,`${name}-${idx+1}.png`)});
  }
 }
 await browser.close();console.log(out);
})().catch(e=>{console.error(e);process.exitCode=1});
