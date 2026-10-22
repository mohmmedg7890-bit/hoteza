/* npm install --no-save playwright; npx playwright install chromium
 * Run: node tests/browser_smoke.cjs
 * Optional BROWSER_PATH=/path/to/chromium for a preinstalled browser.
 * Uses an isolated temporary database and synthetic credentials, never live data.
 */
const {chromium}=require('playwright');
const fs=require('fs'),os=require('os'),path=require('path'),crypto=require('crypto');
const {spawn,execFileSync}=require('child_process');
const assert=require('assert/strict');
const root=path.resolve(__dirname,'..'),tmp=fs.mkdtempSync(path.join(os.tmpdir(),'hoteza-ui-'));
const password=crypto.randomBytes(24).toString('base64url');
const env={...process.env,DEBUG:'1',DATABASE_URL:'',SQLITE_PATH:path.join(tmp,'test.sqlite3'),DEMO_PASSWORD:password};
let server,browser;let serverErrors='',pageErrors=[];
async function main(){
 execFileSync('python',['manage.py','migrate','--noinput'],{cwd:root,env,stdio:'pipe'});
 execFileSync('python',['manage.py','seed_demo'],{cwd:root,env,stdio:'pipe'});
 server=spawn('python',['manage.py','runserver','127.0.0.1:8771','--noreload'],{cwd:root,env,stdio:['ignore','ignore','pipe']});
 server.stderr.on('data',x=>serverErrors+=x);
 for(let i=0;i<80;i++){try{await fetch('http://127.0.0.1:8771/login/');break}catch{await new Promise(r=>setTimeout(r,100))}}
 const options={headless:true};if(process.env.BROWSER_PATH){options.executablePath=process.env.BROWSER_PATH;options.args=['--no-sandbox','--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'];}
 browser=await chromium.launch(options);
 const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
 const p=await context.newPage();p.on('pageerror',e=>pageErrors.push(e.message));
 const wait=()=>p.waitForTimeout(180);
 await p.goto('http://127.0.0.1:8771/');assert((await p.locator('#heroTitle').textContent()).includes('ضيافتك'));await p.locator('[data-modal=offerModal]').first().click();assert(await p.locator('#offerModal').isVisible());await p.locator('#offerModal [data-close]').click();await p.waitForFunction(()=>!document.querySelector('#offerModal').open);await p.goto('http://127.0.0.1:8771/login/');await p.locator('[name=username]').fill('demo-owner');await p.locator('[name=password]').fill(password);await p.getByRole('button',{name:'تسجيل الدخول',exact:true}).click();await p.waitForSelector('.metrics');
 assert.equal(await p.locator('#nav .nav-section').count(),3);
 await p.locator('[data-appearance-open]').click();await p.locator('#appearance-radius').fill('30');await p.locator('#appearance-save').click();assert.equal(await p.evaluate(()=>document.documentElement.style.getPropertyValue('--appearance-radius')),'30px');await p.locator('[data-appearance-close]').click();await p.locator('header [data-appearance-toggle]').click();assert.equal(await p.evaluate(()=>document.documentElement.dataset.appearance),'light');await p.locator('header [data-appearance-toggle]').click();
 const pages=[];
 for(const id of ['dashboard','calendar','reservations','today','units','guests','housekeeping','payments','invoices','balances','reports','users','settings','audit','profile']){
  await p.evaluate(id=>location.hash=id,id);await wait();assert(await p.locator('#page h1').isVisible());pages.push(id);
 }
 async function open(form,id){await p.evaluate(({form,id})=>openForm(form,id),{form,id});await p.waitForSelector('dialog[open]');}
 async function fill(values){for(const [k,v]of Object.entries(values)){const el=p.locator(`#modalform [name="${k}"]`);const tag=await el.evaluate(e=>e.tagName);if(tag==='SELECT')await el.selectOption(String(v));else await el.fill(String(v));}}
 async function save(){await p.locator('#save').click();await p.waitForFunction(()=>!document.querySelector('#modal').open,{},{timeout:5000});await wait();}
 await open('booking');await p.locator('#booking-add-guest').click();await p.locator('[name=phone]').fill('051');assert.equal(await p.locator('[name=phone]').getAttribute('aria-invalid'),'true');await p.locator('#save').click();assert(await p.locator('dialog[open]').isVisible());await fill({name:'نزيل فحص الواجهة',phone:'0500000000',email:'ui@example.com',region:'عسير',city:'أبها',street:'شارع الاختبار'});await p.locator('#save').click();await p.waitForSelector('#stay-nights');assert.equal(await p.locator('#modal-title').textContent(),'حجز جديد');await p.locator('#close-modal').click();
 await open('unit');await fill({number:'UI-901',kind:'استوديو اختبار',floor:'الأول',capacity:2,rate:150});await save();
 await open('unit');await fill({number:'UI-902',kind:'استوديو اختبار',floor:'الأول',capacity:2,rate:150});await save();
 let state=await p.evaluate(()=>S);const guest=state.guests.find(x=>x.name==='نزيل فحص الواجهة'),u=state.units.find(x=>x.number==='UI-901'),v=state.units.find(x=>x.number==='UI-902');
 await open('booking');await fill({guest:guest.id,unit:u.id,arrival:state.today,rate:150,persons:2});await p.locator('[data-nights="7"]').click();assert.equal(await p.locator('#stay-nights').inputValue(),'7');await p.locator('#stay-nights').fill('2');assert.equal(await p.locator('[name=departure]').inputValue(),await p.evaluate(()=>addDays(S.today,2)));assert((await p.locator('#booking-summary').textContent()).includes(await p.evaluate(()=>money(34500))));await save();
 await p.evaluate(()=>location.hash='reservations');await wait();await p.locator('#reservation-status').selectOption('checked_out');assert.equal(await p.locator('#page button[data-open=detail]').count(),0);await p.locator('#reservation-status').selectOption('');
 state=await p.evaluate(()=>S);let r=state.reservations.find(x=>x.guest===guest.id);assert.equal(r.total,34500);
 await open('booking');await fill({guest:guest.id,unit:u.id,arrival:state.today,departure:await p.evaluate(()=>addDays(S.today,1)),rate:150,persons:2});await p.locator('#save').click();await p.waitForSelector('#form-error:not(:empty)');assert((await p.locator('#form-error').textContent()).includes('محجوزة'));await p.locator('#close-modal').click();
 p.on('dialog',d=>d.accept());await open('detail',r.id);await p.locator('dialog [data-action="checkin"]').click();await p.locator('#action-confirm-yes').click();await p.waitForFunction(()=>!document.querySelector('#modal').open);await wait();
 await open('extend',r.id);await fill({departure:await p.evaluate(()=>addDays(S.today,3)),rate:150});await save();
 await open('move',r.id);await fill({unit:v.id});await save();
 await open('charge',r.id);await fill({description:'خدمة فحص',amount:50});await save();
 await open('invoice',r.id);await fill({buyer:'شركة الاختبار'});await save();
 state=await p.evaluate(()=>S);r=state.reservations.find(x=>x.id===r.id);assert.equal(r.total,57500);
 await open('payment',r.id);await fill({amount:575,method:'شبكة',reference:'اختبار واجهة'});await save();
 state=await p.evaluate(()=>S);r=state.reservations.find(x=>x.id===r.id);assert.equal(r.balance,0);assert.equal(r.allocations.at(-1).unit,v.id);
 await open('detail',r.id);assert(await p.locator('dialog').getByText('خدمة فحص',{exact:true}).isVisible());await p.locator('#close-modal').click();
 const inv=r.invoices[0].id;const document=await context.newPage();await document.goto(`http://127.0.0.1:8771/document/invoice/${inv}/`);assert((await document.locator('h1').textContent()).includes('فاتورة'));
 fs.mkdirSync(path.join(root,'test-results'),{recursive:true});await document.screenshot({path:path.join(root,'test-results/invoice-desktop.png'),fullPage:true});
 for(const fmt of ['pdf','xlsx','docx','csv','png','json']){const response=await context.request.get(`http://127.0.0.1:8771/export/invoice-${inv}/${fmt}/`);assert.equal(response.status(),200);assert((await response.body()).length>20)}
 await document.close();
 await p.evaluate(()=>location.hash='calendar');await wait();let tomorrow=await p.evaluate(()=>addDays(S.today,1));await p.locator('#calendar-start').fill(tomorrow);await p.locator('#calendar-start').dispatchEvent('change');await wait();assert.equal(await p.locator('#calendar-start').inputValue(),tomorrow);
 await p.evaluate(()=>location.hash='reports');await wait();await p.locator('#report-start').fill(state.today);await p.locator('#report-end').fill(await p.evaluate(()=>addDays(S.today,4)));await p.locator('#run-report').click();await wait();assert.equal(await p.locator('#report-result table').first().locator('tbody tr').count(),4);
 await p.reload();await p.waitForSelector('#page h1');assert((await p.evaluate(()=>S.reservations.find(x=>x.id===Number(location.search.slice(1)))||S.guests.some(x=>x.name==='نزيل فحص الواجهة'))));
 await p.evaluate(()=>location.hash='dashboard');await wait();await p.screenshot({path:path.join(root,'test-results/dashboard-desktop.png'),fullPage:true});
 await p.setViewportSize({width:390,height:844});await p.screenshot({path:path.join(root,'test-results/dashboard-mobile.png'),fullPage:true});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
 await p.locator('#menu').click();assert(await p.locator('#sidebar').isVisible());await p.locator('#nav a[href="#units"]').click();await wait();assert.equal(await p.locator('#page h1').textContent(),'الوحدات');
 await p.setViewportSize({width:1440,height:1000});const other=state.property.id===1?'2':'1';await p.locator('#property').selectOption(other);await wait();assert.equal(await p.evaluate(()=>S.guests.some(x=>x.name==='نزيل فحص الواجهة')),false);
 assert.deepEqual(pageErrors,[]);
 console.log(JSON.stringify({status:'passed',pages:pages.length,flow:['guest','units','booking','conflict','checkin','extend','move','charge','invoice','payment','documents','6 exports','calendar range','report period','reload','mobile','tenant switch'],pageErrors}));
}
main().catch(e=>{console.error(e);console.error(serverErrors.slice(-4000));process.exitCode=1}).finally(async()=>{if(browser)await browser.close();if(server)server.kill();fs.rmSync(tmp,{recursive:true,force:true})});
