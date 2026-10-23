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
 await p.goto('http://127.0.0.1:8771/');assert((await p.locator('#heroTitle').textContent()).includes('ضيافتك'));await p.locator('[data-modal=offerModal]').first().click();assert(await p.locator('#offerModal').isVisible());await p.locator('#offerModal .modal-close').click();await p.waitForFunction(()=>!document.querySelector('#offerModal').open);await p.goto('http://127.0.0.1:8771/login/');await p.locator('[name=username]').fill('demo-owner');await p.locator('[name=password]').fill(password);await p.getByRole('button',{name:'تسجيل الدخول',exact:true}).click();await p.waitForSelector('.metrics');
 assert.equal(await p.locator('#nav .nav-section').count(),3);
 // New ledger foundation: explicit owner approval, balanced posting, reversal and read-only reports.
 await p.locator('#nav a[href="#ledger"]').click();await p.waitForSelector('#ledger-result .notice');
 await p.locator('[data-action=journal_init]').click();await p.locator('#action-confirm-yes').click();await p.waitForSelector('#ledger-result tbody tr:nth-child(12)');
 await p.locator('[data-open=ledger_opening]').click();await p.locator('[name=reference]').fill('UI-OPEN-ZERO');await p.locator('[name=confirm_zero]').selectOption('1');await p.locator('#save').click();await p.locator('#action-confirm-yes').click();await p.waitForFunction(()=>!document.querySelector('#modal').open);await p.waitForFunction(()=>!document.querySelector('[data-open=ledger_opening]'));
 await p.locator('[data-open=journal_entry]').click();await p.locator('[name=description]').fill('قيد اختبار واجهة');await p.locator('[name=account_0]').selectOption('1000');await p.locator('[name=debit_0]').fill('100');await p.locator('[name=account_1]').selectOption('3000');await p.locator('[name=credit_1]').fill('100');await p.locator('#save').click();await p.locator('#action-confirm-yes').click();await p.waitForFunction(()=>!document.querySelector('#modal').open);await p.waitForSelector('[data-ledger-reverse]');
 await p.locator('#ledger-account-filter').selectOption('1000');assert((await p.locator('#ledger-entries').textContent()).includes('قيد اختبار واجهة'));
 await p.locator('[data-open=ledger_reconcile]').click();await p.locator('[name=reference]').fill('UI-CASH-RECON');await p.locator('[name=actual]').fill('100');await p.locator('#ledger-reconcile-preview').click();await p.waitForSelector('#ledger-reconcile-result table');await p.locator('#save').click();await p.locator('#action-confirm-yes').click();await p.waitForFunction(()=>!document.querySelector('#modal').open);await p.waitForFunction(()=>document.querySelector('#ledger-result')?.textContent.includes('متطابق عند التسجيل'));
 await p.locator('[data-ledger-reverse]').first().click();await p.locator('[name=description]').fill('عكس اختبار واجهة');await p.locator('#save').click();await p.locator('#action-confirm-yes').click();await p.waitForFunction(()=>!document.querySelector('#modal').open);await p.waitForFunction(()=>document.querySelector('#ledger-entries')?.textContent.includes('تم عكسه'));await p.waitForFunction(()=>document.querySelector('#ledger-result')?.textContent.includes('تغير الدفتر؛ أعد المطابقة'));

 await p.locator('#nav a[href="#units"]').click();await p.waitForSelector('.board-grid');
 assert((await p.locator('.board-room').count())>0);
 await p.locator('[data-board-view=list]').click();assert(await p.locator('.room-board table').isVisible());
 await p.locator('[data-board-view=grid]').click();await p.locator('[data-board-unit]').first().click();await p.waitForSelector('#modal[open]');await p.locator('#close-modal').click();
 await p.locator('[data-board-clean=other]').click();await p.locator('[data-board-clean=all]').click();
 await p.locator('[data-board-filter=vacant]').click();assert.equal(await p.locator('.board-room:not(.board-vacant)').count(),0);
 const vacant=p.locator('.board-room [data-open=booking]').first();if(await vacant.count()){const unit=await vacant.getAttribute('data-unit');await vacant.click();await p.waitForSelector('#modal[open]');assert.equal(await p.locator('#modal [name=unit]').inputValue(),unit);await p.locator('#close-modal').click();}
 await p.locator('[data-board-filter=all]').click();

 // Repeated modal closure must release pointer hit-testing; exercise real clicks, not evaluate(openForm).
 for(let i=0;i<3;i++){
  await p.locator('#nav a[href="#guests"]').click();await p.getByRole('button',{name:'إضافة نزيل',exact:true}).click();await p.locator('#close-modal').click();
  await p.locator('#nav a[href="#reports"]').click();await p.locator('[data-report-view=units]').click();await p.waitForFunction(()=>document.querySelector('[data-report-view=units]').getAttribute('aria-selected')==='true');
  assert.equal(await p.locator('dialog[open]').count(),0);
 }
 await p.locator('[data-report-view=overview]').click();
 // Exercise the appearance dialog too, then hit-test a real reservation button.
 await p.locator('[data-appearance-open]').click();await p.locator('[data-appearance-close]').click();await p.locator('#nav a[href="#reservations"]').click();const firstReservation=p.locator('[data-open=detail]').first();await firstReservation.click();await p.waitForSelector('#modal[open]');await p.locator('#close-modal').click();


 await p.locator('[data-appearance-open]').click();await p.locator('#appearance-radius').fill('30');await p.locator('#appearance-save').click();assert.equal(await p.evaluate(()=>document.documentElement.style.getPropertyValue('--appearance-radius')),'30px');await p.locator('[data-appearance-close]').click();await p.locator('header [data-appearance-toggle]').click();assert.equal(await p.evaluate(()=>document.documentElement.dataset.appearance),'light');await p.locator('header [data-appearance-toggle]').click();
 const pages=[];
 for(const id of ['dashboard','calendar','reservations','today','units','guests','housekeeping','payments','invoices','balances','reports','users','settings','audit','profile']){
  await p.evaluate(id=>location.hash=id,id);await wait();assert(await p.locator('#page h1').isVisible());pages.push(id);
 }
 async function open(form,id){await p.evaluate(({form,id})=>openForm(form,id),{form,id});await p.waitForSelector('dialog[open]');}
 async function fill(values){for(const [k,v]of Object.entries(values)){const el=p.locator(`#modalform [name="${k}"]`);const tag=await el.evaluate(e=>e.tagName);if(tag==='SELECT')await el.selectOption(String(v));else await el.fill(String(v));}}
 async function save(){await p.locator('#save').click();await p.waitForFunction(()=>!document.querySelector('#modal').open,{},{timeout:5000});await wait();}
 await open('booking');await p.locator('#booking-add-guest').click();await p.locator('[name=phone]').fill('051');assert.equal(await p.locator('[name=phone]').getAttribute('aria-invalid'),'true');await p.locator('#save').click();assert(await p.locator('dialog[open]').isVisible());await fill({first_name:'نزيل',second_name:'فحص',last_name:'الواجهة',gender:'male',birth_date:'1990-01-01',nationality:'السعودية',customer_type:'citizen',id_type:'national_id',id_number:'1000000000',phone:'0500000000',email:'ui@example.com',region:'عسير',city:'أبها',street:'شارع الاختبار'});await p.waitForFunction(()=>document.querySelector('[name=birth_hijri]').value);await p.locator('#save').click();await p.waitForSelector('#stay-nights');assert.equal(await p.locator('#modal-title').textContent(),'حجز جديد');await p.locator('#close-modal').click();
 await open('unit');await fill({number:'UI-901',kind:'استوديو اختبار',floor:'الأول',capacity:2,rate:150});await save();
 await open('unit');await fill({number:'UI-902',kind:'استوديو اختبار',floor:'الأول',capacity:2,rate:150});await save();
 let state=await p.evaluate(()=>S);const guest=state.guests.find(x=>x.name==='نزيل فحص الواجهة'),u=state.units.find(x=>x.number==='UI-901'),v=state.units.find(x=>x.number==='UI-902');
 await open('booking');await fill({guest:guest.id,unit:u.id,arrival:state.today,rate:150,persons:2});await p.locator('[data-nights="7"]').click();assert.equal(await p.locator('#stay-nights').inputValue(),'7');await p.locator('#stay-nights').fill('2');assert.equal(await p.locator('[name=departure]').inputValue(),await p.evaluate(()=>addDays(S.today,2)));assert((await p.locator('#booking-summary').textContent()).includes(await p.evaluate(()=>money(34500))));await save();
 await p.evaluate(()=>location.hash='reservations');await wait();await p.locator('#reservation-status').selectOption('checked_out');assert.equal(await p.locator('#page button[data-open=detail]').count(),0);await p.locator('#reservation-status').selectOption('');
 state=await p.evaluate(()=>S);let r=state.reservations.find(x=>x.guest===guest.id);assert.equal(r.total,34500);
 await open('booking');await fill({guest:guest.id,unit:u.id,arrival:state.today,departure:await p.evaluate(()=>addDays(S.today,1)),rate:150,persons:2});await p.locator('#save').click();await p.waitForSelector('#form-error:not(:empty)');assert((await p.locator('#form-error').textContent()).includes('محجوزة'));await p.locator('#close-modal').click();
 p.on('dialog',d=>d.accept());await open('detail',r.id);await p.locator('.reservation-bottom-actions [data-action="checkin"]').click();await p.locator('#action-confirm-yes').click();await p.waitForFunction(()=>!document.querySelector('#modal').open);await wait();
 await open('extend',r.id);await fill({departure:await p.evaluate(()=>addDays(S.today,3)),rate:150});await save();
 await open('move',r.id);await fill({unit:v.id});await save();
 await open('charge',r.id);await fill({description:'خدمة فحص',amount:50});await save();
 await open('invoice',r.id);await fill({buyer:'شركة الاختبار'});await save();
 state=await p.evaluate(()=>S);r=state.reservations.find(x=>x.id===r.id);assert.equal(r.total,57500);
 await open('payment',r.id);await fill({amount:575,method:'شبكة',reference:'اختبار واجهة'});await save();
 state=await p.evaluate(()=>S);r=state.reservations.find(x=>x.id===r.id);assert.equal(r.balance,0);assert.equal(r.allocations.at(-1).unit,v.id);
 await open('detail',r.id);assert(await p.locator('dialog').getByText('خدمة فحص',{exact:true}).isVisible());await p.locator('[data-booking-tab=finance]').click();await p.locator('[data-finance-tab=receipts]').click();assert((await p.locator('#fields').textContent()).includes('PAY-'));await p.locator('[data-finance-tab=expenses]').click();assert((await p.locator('#fields').textContent()).includes('لا يعتبر تحصيلًا'));await p.locator('#close-modal').click();
 await p.locator('#nav a[href="#guests"]').click();await p.getByRole('button',{name:'إضافة نزيل',exact:true}).click();await p.locator('#close-modal').click();
 // A separate monthly reservation, including its additional-unit row, is saved to the backend.
 await open('booking');await fill({guest:guest.id,unit:u.id,arrival:await p.evaluate(()=>addDays(S.today,10)),rate:2800,rental_type:'monthly',persons:2});await p.locator('[data-add-booking-unit]').click();await p.locator('[data-extra-row] select').selectOption(String(v.id));await p.locator('[data-extra-row] input').fill('1400');await p.locator('[name=discount_type]').selectOption('percent');await p.locator('[name=discount_value]').fill('10');await save();
 let monthly=await p.evaluate(()=>S.reservations.find(x=>x.rental_type==='monthly'));assert.equal(monthly.allocations.length,2);assert.equal(monthly.net,378000);assert(monthly.contract);
 const contractPage=await context.newPage();await contractPage.goto(`http://127.0.0.1:8771/document/contract/${monthly.contract}/`);assert((await contractPage.locator('body').textContent()).includes('مسودة غير مكتملة'));await contractPage.close();

 // Checkout must invoice automatically and retain visible print links without a popup blocker.
 await open('unit');await fill({number:'UI-903',kind:'اختبار مغادرة',floor:'الأول',capacity:2,rate:100});await save();
 const checkoutUnit=await p.evaluate(()=>S.units.find(u=>u.number==='UI-903').id);
 await open('booking');await fill({guest:guest.id,unit:checkoutUnit,arrival:state.today,departure:await p.evaluate(()=>addDays(S.today,1)),rate:100,persons:1});await save();
 const checkoutId=await p.evaluate(id=>S.reservations.find(r=>r.allocations.some(a=>a.unit===id)).id,checkoutUnit);
 await open('detail',checkoutId);await p.locator('.reservation-bottom-actions [data-action=checkin]').click();await p.locator('#action-confirm-yes').click();await p.waitForFunction(()=>!document.querySelector('#modal').open);
 await open('payment',checkoutId);await fill({amount:115,method:'نقد'});await save();
 await open('checkout',checkoutId);await fill({allow_same_day:'1'});await p.locator('#save').click();await p.waitForSelector('.checkout-success');
 const checkoutInvoice=p.locator('.checkout-success a[href^="/document/invoice/"]');assert.equal(await checkoutInvoice.count(),1);
 const printed=await context.newPage();await printed.goto('http://127.0.0.1:8771'+await checkoutInvoice.getAttribute('href'));assert((await printed.locator('h1').textContent()).includes('فاتورة'));await printed.close();
 await p.locator('#close-modal').click();await open('detail',checkoutId);assert(await p.locator('.reservation-bottom-actions a[href^="/document/invoice/"]').isVisible());await p.locator('#close-modal').click();

 // Review source-backed journals from the completed stay; repeated review adds nothing.
 await p.locator('#nav a[href="#ledger"]').click();await p.waitForSelector('#ledger-source-id');await p.locator('#ledger-source-id').selectOption(String(checkoutId));await p.locator('#ledger-source-preview').click();await p.waitForSelector('[data-action=journal_import]');
 await p.locator('[data-action=journal_import]').click();await p.locator('#action-confirm-yes').click();await p.waitForSelector('#ledger-source-id');await p.locator('#ledger-source-id').selectOption(String(checkoutId));await p.locator('#ledger-source-preview').click();await p.waitForFunction(()=>document.querySelector('#ledger-source-plan')?.textContent.includes('لا توجد قيود جديدة'));
 await p.locator('[data-open=ledger_transfer]').click();await p.locator('[name=amount]').fill('20');await p.locator('[name=fee]').fill('1');await p.locator('[name=reference]').fill('UI-BANK-TRANSFER');await p.locator('#save').click();await p.locator('#action-confirm-yes').click();await p.waitForFunction(()=>!document.querySelector('#modal').open);await p.waitForSelector('[data-open=ledger_reconcile]');await p.locator('[data-open=ledger_reconcile]').click();await p.locator('[name=account]').selectOption('1010');await p.locator('[name=actual]').fill('19');await p.locator('[name=reference]').fill('UI-BANK-RECON');await p.locator('#ledger-reconcile-preview').click();await p.waitForSelector('#ledger-reconcile-result table');assert((await p.locator('#ledger-reconcile-result').textContent()).includes('متطابق عند المعاينة'));await p.locator('#close-modal').click();
 const inv=r.invoices[0].id;const document=await context.newPage();await document.goto(`http://127.0.0.1:8771/document/invoice/${inv}/`);assert((await document.locator('h1').textContent()).includes('فاتورة'));
 fs.mkdirSync(path.join(root,'test-results'),{recursive:true});await document.screenshot({path:path.join(root,'test-results/invoice-desktop.png'),fullPage:true});
 for(const fmt of ['pdf','xlsx','docx','csv','png','json']){const response=await context.request.get(`http://127.0.0.1:8771/export/invoice-${inv}/${fmt}/`);assert.equal(response.status(),200);assert((await response.body()).length>20)}
 await document.close();
 await p.evaluate(()=>location.hash='calendar');await wait();let tomorrow=await p.evaluate(()=>addDays(S.today,1));await p.locator('#calendar-start').fill(tomorrow);await p.locator('#calendar-start').dispatchEvent('change');await wait();assert.equal(await p.locator('#calendar-start').inputValue(),tomorrow);
 await p.evaluate(()=>location.hash='reports');await wait();await p.locator('[data-report-view=overview]').click();await p.locator('#report-start').fill(state.today);await p.locator('#report-end').fill(await p.evaluate(()=>addDays(S.today,4)));await p.locator('#run-report').click();await wait();assert.equal(await p.locator('#report-result table').first().locator('tbody tr').count(),5);
 await p.locator('[data-report-view=units]').click();assert((await p.locator('#report-result h2').textContent()).includes('أداء الوحدات'));assert((await p.locator('a.export').first().getAttribute('href')).includes('view=units'));await p.reload();await p.waitForSelector('#page h1');assert((await p.evaluate(()=>S.reservations.find(x=>x.id===Number(location.search.slice(1)))||S.guests.some(x=>x.name==='نزيل فحص الواجهة'))));
 await p.evaluate(()=>location.hash='dashboard');await wait();await p.screenshot({path:path.join(root,'test-results/dashboard-desktop.png'),fullPage:true});
 await p.setViewportSize({width:390,height:844});await p.screenshot({path:path.join(root,'test-results/dashboard-mobile.png'),fullPage:true});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
 await p.locator('#menu').click();assert(await p.locator('#sidebar').isVisible());await p.locator('#nav a[href="#units"]').click();await wait();assert.equal(await p.locator('#page h1').textContent(),'الوحدات');
 await p.setViewportSize({width:1440,height:1000});const other=state.property.id===1?'2':'1';await p.locator('#property').selectOption(other);await wait();assert.equal(await p.evaluate(()=>S.guests.some(x=>x.name==='نزيل فحص الواجهة')),false);
 assert.deepEqual(pageErrors,[]);
 console.log(JSON.stringify({status:'passed',pages:pages.length,flow:['guest','units','booking','conflict','checkin','extend','move','charge','invoice','payment','documents','6 exports','calendar range','report period','reload','mobile','tenant switch'],pageErrors}));
}
main().catch(e=>{console.error(e);console.error(serverErrors.slice(-4000));process.exitCode=1}).finally(async()=>{if(browser)await browser.close();if(server)server.kill();fs.rmSync(tmp,{recursive:true,force:true})});
