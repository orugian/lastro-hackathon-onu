import {createRequire} from 'node:module';
import {mkdir,writeFile} from 'node:fs/promises';
const require=createRequire(process.env.PLAYWRIGHT_PACKAGE || 'C:/Users/orugi/AppData/Local/npm-cache/_npx/e41f203b7505f1fb/node_modules/playwright/package.json');
const {chromium}=require('playwright');
const browser=await chromium.launch({headless:true,args:['--use-angle=swiftshader','--enable-webgl']});
const page=await browser.newPage({viewport:{width:1440,height:900}});
await page.route('**/api/health',r=>r.abort());
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const round=process.argv[2]||'round1';await mkdir(`tests/web/screens/${round}`,{recursive:true});
for(const [name,hash] of [['triagem','#/'],['dossie','#/caso/MOCK-POA-0001'],['confiabilidade','#/confiabilidade']]){
 await page.goto(`http://127.0.0.1:5173/${hash}`);await page.waitForTimeout(2500);await page.screenshot({path:`tests/web/screens/${round}/${name}.png`,fullPage:true});
 if(name==='dossie'){await page.getByText('Volume declarado sem lastro observável',{exact:true}).click();await page.locator('button.evidence:not(:disabled)').first().click();await page.waitForTimeout(600);await page.getByLabel('Comparar antes e depois').fill('28');await page.locator('.map-tools select').selectOption('CBERS-4A WPM');await page.waitForTimeout(2000);await page.screenshot({path:`tests/web/screens/${round}/dossie-evidencia.png`,fullPage:true});}
}
await page.goto('http://127.0.0.1:5173/#/');await page.getByRole('heading',{name:'Triagem territorial'}).waitFor();await page.getByLabel('Só com imagem').check();if(await page.locator('.case-row').count()!==2)throw Error('Filtro de imagem incorreto');
await page.locator('.filter-bar select').nth(0).selectOption('RO');await page.locator('.filter-bar select').nth(1).selectOption('POA');await page.getByText('Nenhuma autorização corresponde aos filtros.',{exact:false}).waitFor();
await page.getByRole('button',{name:'Analisar autorização',exact:false}).click();await page.getByLabel('Número AUTEX').fill('123');await page.getByRole('button',{name:'Iniciar análise'}).click();await page.getByText('A análise precisa da API local',{exact:false}).waitFor();await page.getByRole('button',{name:'Fechar',exact:true}).click();
for(const width of [1280,390]){await page.setViewportSize({width,height:width===1280?720:844});await page.goto('http://127.0.0.1:5173/#/caso/MOCK-POA-0001');await page.waitForTimeout(2000);await page.screenshot({path:`tests/web/screens/${round}/dossie-${width}.png`,fullPage:true});const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);if(overflow)throw Error(`Overflow ${width}`)}
await writeFile(`tests/web/screens/${round}/results.json`,JSON.stringify({errors,checks:['three routes','image filter','empty filters','evidence focus','sensor switch','swipe','offline analysis error','responsive 1280 and 390']},null,2));await browser.close();if(errors.length)throw Error(errors.join('\n'));console.log('PASS: 3 rotas, filtros, evidência, sensor, swipe, erro offline e responsividade; 0 pageerrors');
