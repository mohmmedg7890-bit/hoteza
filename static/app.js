'use strict';
let S=null, page='dashboard', search='', reportData=null, selected=0, modalAction=null, modalTransform=null, operationKey=null, calendarStart='';
const $=s=>document.querySelector(s), esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=n=>(Number(n||0)/100).toLocaleString('ar-SA',{minimumFractionDigits:2,maximumFractionDigits:2});
const addDays=(s,n)=>{const d=new Date(s+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10)};
const labels={confirmed:'مؤكد',checked_in:'مقيم',checked_out:'مغادر',cancelled:'ملغى',no_show:'لم يحضر',ready:'جاهزة',dirty:'تحتاج تنظيفًا',cleaning:'قيد التنظيف',invoice:'فاتورة',credit:'إشعار دائن',debit:'إشعار مدين',owner:'مالك',reception:'استقبال'};
const nav=[['dashboard','لوحة المعلومات'],['calendar','تقويم الوحدات'],['reservations','الحجوزات'],['today','حركة اليوم'],['units','الوحدات'],['guests','النزلاء'],['housekeeping','النظافة والصيانة'],['payments','التحصيل والسندات'],['invoices','الفواتير'],['balances','التسويات والمديونيات'],['reports','التقارير'],['users','المستخدمون'],['settings','الإعدادات'],['audit','سجل العمليات'],['profile','حسابي']];
function csrf(){return document.cookie.split('; ').find(x=>x.startsWith('csrftoken='))?.split('=')[1]||''}
async function request(url,opts={}){const r=await fetch(url,{credentials:'same-origin',...opts});if(r.status===401){location.href='/login/';throw Error('انتهت الجلسة')}let d;try{d=await r.json()}catch{throw Error('تعذر قراءة استجابة الخادم')}if(!r.ok)throw Error(d.error||'تعذر إتمام العملية');return d}
async function mutate(action,data,key=crypto.randomUUID()){return request('/api/action/'+action+'/',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf(),'Idempotency-Key':key},body:JSON.stringify(data)})}
function toast(s){$('#toast').textContent=s;$('#toast').style.display='block';setTimeout(()=>$('#toast').style.display='none',4000)}
async function load(){S=await request('/api/state/');$('#property').value=S.property.id;$('#identity').textContent=S.user+' · '+labels[S.role];render()}
function tag(s){return `<span class="tag ${['ready','checked_in'].includes(s)?'green':['cancelled','dirty'].includes(s)?'red':''}">${esc(labels[s]||s)}</span>`}
function btn(label,action,data={},cls=''){return `<button class="${cls}" data-action="${esc(action)}" data-payload="${esc(JSON.stringify(data))}">${esc(label)}</button>`}
function openBtn(label,form,id=''){return `<button data-open="${form}" data-id="${id}">${esc(label)}</button>`}
function linkDoc(label,kind,id){return `<a class="button" target="_blank" rel="noopener" href="/document/${kind}/${id}/">${esc(label)}</a>`}
function table(headers,rows){return `<div class="tablewrap"><table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.length?rows.map(r=>'<tr>'+r.map(c=>`<td>${c}</td>`).join('')+'</tr>').join(''):`<tr><td class="empty" colspan="${headers.length}">لا توجد بيانات لهذه القائمة</td></tr>`}</tbody></table></div>`}
function exportsBar(dataset){return `<div class="toolbar no-print"><span>تصدير:</span>${['pdf','xlsx','docx','csv','png','json'].map(f=>`<a class="button export" data-dataset="${dataset}" href="/export/${dataset}/${f}/">${f.toUpperCase()}</a>`).join('')}<button data-print>معاينة / طباعة</button></div>`}
function head(title,desc,actions=''){return `<div class="pagehead"><div><div class="eyebrow">HOTEZA / OPERATIONS</div><h1>${title}</h1><p>${desc}</p></div><div class="actions">${actions}</div></div>`}
function searchbar(){return `<div class="toolbar"><input id="search" aria-label="بحث" placeholder="ابحث بالاسم أو الرقم…" value="${esc(search)}"></div>`}
function resRows(rs){return rs.map(r=>[openBtn('#'+r.id,'detail',r.id),esc(r.guest_name),esc(r.allocations.at(-1)?.number||'—'),esc(r.arrival),esc(r.departure),tag(r.status),money(r.total),money(r.balance)])}
function resTable(rs){return table(['الحجز','النزيل','الوحدة','الوصول','المغادرة','الحالة','الإجمالي','المتبقي'],resRows(rs))}
function filtered(rs){const q=search.toLowerCase();return rs.filter(r=>[r.id,r.guest_name,r.phone,r.source].some(v=>String(v).toLowerCase().includes(q)))}
function allPayments(){return S.reservations.flatMap(r=>r.payments.map(p=>({...p,reservation:r.id,guest:r.guest_name})))}
function allInvoices(){return S.reservations.flatMap(r=>r.invoices.map(i=>({...i,reservation:r.id,guest:r.guest_name})))}
function occupied(u,date=S.today){return S.reservations.find(r=>!['cancelled','no_show'].includes(r.status)&&r.allocations.some(a=>a.unit===u.id&&a.start<=date&&a.end>date))}
function reportHTML(r){return `<div class="metrics">${[['الإشغال',r.occupancy+'%'],['الليالي المباعة',r.sold],['الإيراد قبل الضريبة',money(r.net)],['صافي التحصيل',money(r.paid)],['الطاقة بالليالي',r.capacity],['الضريبة',money(r.tax)],['ADR قبل الضريبة',money(r.adr)],['RevPAR قبل الضريبة',money(r.revpar)]].map(([k,v])=>`<div class="metric">${k}<strong>${v}</strong></div>`).join('')}</div>`+table(['اليوم','الطاقة','المباع','الإيراد قبل الضريبة','الضريبة','صافي التحصيل'],r.rows.map(x=>[x.date,x.available,x.sold,money(x.net),money(x.tax),money(x.paid)]))+`<h2>بحسب مصدر الحجز</h2>`+table(['المصدر','الليالي','الإيراد قبل الضريبة','الضريبة'],r.by_source.map(x=>[esc(x.source),x.sold,money(x.net),money(x.tax)]))+`<h2>أداء الوحدات — يشمل الفارغة</h2>`+table(['الوحدة','النوع','الطاقة','المباع','الإشغال %','الإيراد قبل الضريبة','الضريبة'],r.by_unit.map(x=>[esc(x.number),esc(x.kind),x.capacity,x.sold,x.capacity?(100*x.sold/x.capacity).toFixed(2):'0',money(x.net),money(x.tax)]))}
function render(){
 if(!S)return;page=(location.hash.slice(1).split('?')[0]||'dashboard');const title=nav.find(n=>n[0]===page)?.[1]||'لوحة المعلومات';
 $('#nav').innerHTML=nav.filter(([id])=>S.role==='owner'||!['users','settings','audit'].includes(id)).map(([id,n])=>`<a href="#${id}" class="navitem ${page===id?'active':''}">${n}</a>`).join('');$('#breadcrumb').textContent=title;document.title=title+' | Hoteza';
 let h='';
 if(page==='dashboard'){
 const arriving=S.reservations.filter(r=>r.arrival===S.today&&r.status==='confirmed'),leaving=S.reservations.filter(r=>r.departure<=S.today&&r.status==='checked_in'),inhouse=S.reservations.filter(r=>r.status==='checked_in');
 h=head('التشغيل تحت السيطرة',esc(S.property.name)+' · '+S.today,openBtn('حجز جديد','booking'));
 h+=`<div class="metrics">${[['إشغال الليالي اليوم',S.report.occupancy+'%','reports'],['المقيمون الآن',inhouse.length,'today'],['وصول اليوم',arriving.length,'today'],['مغادرة مستحقة',leaving.length,'today'],['تحصيل اليوم',money(S.report.paid),'payments'],['مديونيات الحجوزات',money(S.reservations.reduce((n,r)=>n+Math.max(r.balance,0),0)),'balances'],['جاهزة وغير محجوزة',S.units.filter(u=>u.active&&u.cleaning==='ready'&&!occupied(u)&&!S.blocks.some(b=>b.unit_id===u.id&&b.start<=S.today&&b.end>S.today)).length,'units'],['تحتاج تنظيفًا',S.units.filter(u=>u.cleaning==='dirty').length,'housekeeping']].map(([k,v,to])=>`<button class="metric" data-go="${to}">${k}<strong>${v}</strong><small>عرض التفاصيل ←</small></button>`).join('')}</div>`;
 h+=`<div class="card"><h2>الوصول المتوقع اليوم</h2>${resTable(arriving)}</div><br><div class="card"><h2>المغادرة والمتأخرون</h2>${resTable(leaving)}</div>`;
 } else if(page==='reservations'){h=head(title,'من أول حجز إلى إقفال حساب الإقامة',openBtn('حجز جديد','booking'))+searchbar()+resTable(filtered(S.reservations))+exportsBar('reservations');
 } else if(page==='today'){
 h=head(title,'قوائم مشتقة من الحجوزات نفسها؛ افتح الحجز لتنفيذ العملية');
 const groups=[['الوصول المتوقع',r=>r.arrival===S.today&&r.status==='confirmed'],['المقيمون',r=>r.status==='checked_in'],['المغادرة اليوم',r=>r.departure===S.today&&r.status==='checked_in'],['متأخرون عن المغادرة',r=>r.departure<S.today&&r.status==='checked_in'],['وصول سابق لم يسكن',r=>r.arrival<S.today&&r.status==='confirmed']];h+=groups.map(([n,f])=>`<section class="card"><h2>${n}</h2>${resTable(S.reservations.filter(f))}</section><br>`).join('');
 } else if(page==='calendar'){
 let start=calendarStart||S.today;const ds=Array.from({length:14},(_,i)=>addDays(start,i));h=head(title,'14 يومًا · اضغط الحجز لفتحه أو المساحة المتاحة لإنشائه')+`<div class="toolbar"><label>بداية العرض<input id="calendar-start" type="date" value="${start}"></label></div><div class="tablewrap calendar"><table><thead><tr><th>الوحدة</th>${ds.map(d=>`<th>${d.slice(5)}</th>`).join('')}</tr></thead><tbody>${S.units.filter(u=>u.active).map(u=>'<tr><th>'+esc(u.number)+'<small> '+esc(u.kind)+'</small></th>'+ds.map(d=>{const r=occupied(u,d),b=S.blocks.find(b=>b.unit_id===u.id&&b.start<=d&&b.end>d);return `<td class="${r?'stay':b?'maintenance':''}">${r?openBtn(r.guest_name,'detail',r.id):b?esc(b.reason):`<button data-open="booking" data-unit="${u.id}" data-date="${d}">＋</button>`}</td>`}).join('')+'</tr>').join('')}</tbody></table></div>`;
 } else if(page==='units'){
 h=head(title,'الطوابق والأنواع والسعة وحالة تجهيز الوحدة',S.role==='owner'?openBtn('إضافة وحدة','unit'):'')+searchbar()+`<div class="unitgrid">${S.units.filter(u=>[u.number,u.kind,u.floor].join(' ').includes(search)).map(u=>{const r=occupied(u);return `<div class="unitcard ${r?'busy':u.cleaning==='dirty'?'dirty':''}"><strong>${esc(u.number)}</strong><small>${esc(u.kind)} · ${esc(u.floor)}</small>${tag(u.cleaning)}<p>${money(u.rate)} ر.س / ليلة · سعة ${u.capacity}</p>${r?openBtn('الحجز #'+r.id,'detail',r.id):'<small>راجع التقويم للتوافر</small>'}${S.role==='owner'?openBtn('تعديل','unit',u.id):''}${!u.active?tag('مؤرشفة'):''}</div>`}).join('')}</div>`;
 } else if(page==='guests'){
 h=head(title,'ملف موحد لكل نزيل وسجل إقاماته',openBtn('إضافة نزيل','guest'))+searchbar()+table(['النزيل','الجوال','البريد','الحجوزات','الإجراءات'],S.guests.filter(g=>[g.name,g.phone].join(' ').includes(search)).map(g=>[esc(g.name),esc(g.phone||'غير متاح'),esc(g.email||'—'),openBtn('عرض السجل','guest_detail',g.id),openBtn('تعديل','guest',g.id)]))+exportsBar('guests');
 } else if(page==='housekeeping'){
 h=head(title,'فصل التنظيف عن التوافر؛ الصيانة تحجب الفترة المحددة',openBtn('حجب للصيانة','block'))+table(['الوحدة','النوع','الحالة','الإجراء'],S.units.filter(u=>u.active).map(u=>[esc(u.number),esc(u.kind),tag(u.cleaning),btn('بدء التنظيف','cleaning',{id:u.id,cleaning:'cleaning'})+' '+btn('جاهزة','cleaning',{id:u.id,cleaning:'ready'})+' '+btn('تحتاج تنظيفًا','cleaning',{id:u.id,cleaning:'dirty'})]));
 h+='<h2>فترات الصيانة</h2>'+table(['الوحدة','من','إلى - غير مشمول','السبب','الإجراء'],S.blocks.map(b=>[esc(S.units.find(u=>u.id===b.unit_id)?.number),b.start,b.end,esc(b.reason),S.role==='owner'?btn('إزالة الحجب','block_remove',{id:b.id}):'—']));
 } else if(page==='payments'){
 h=head(title,'سند مستقل لكل قبض أو رد مبلغ',openBtn('تسجيل دفعة','payment'))+table(['السند','الحجز','النزيل','المبلغ','الطريقة','التاريخ','المستند'],allPayments().map(p=>['PAY-'+p.id,openBtn('#'+p.reservation,'detail',p.reservation),esc(p.guest),money(p.amount),esc(p.method),esc(p.date.slice(0,16)),linkDoc('معاينة','receipt',p.id)]))+exportsBar('payments');
 } else if(page==='invoices'){
 h=head(title,'صور ثابتة عند الإصدار؛ التصحيح بمستند مرتبط. الفوترة هنا تجريبية.',openBtn('إصدار فاتورة','invoice'))+table(['المستند','النوع','الحجز','المشتري / النزيل','الإجمالي','مرجع الأصل','المعاينة'],allInvoices().map(i=>['INV-'+i.id,tag(i.kind),openBtn('#'+i.reservation,'detail',i.reservation),esc(i.guest),money(i.total),i.reference||'—',linkDoc('فتح','invoice',i.id)]));
 } else if(page==='balances'){
 h=head(title,'القيمة الموجبة على النزيل، والسالبة لصالحه')+resTable(S.reservations.filter(r=>r.balance!==0));
 } else if(page==='reports'){
 const from=$('#report-start')?.value||S.today,to=$('#report-end')?.value||addDays(S.today,1);
 h=head(title,'نهاية الفترة غير مشمولة · الإيراد منفصل عن المقبوض')+`<div class="toolbar"><label>من<input id="report-start" type="date" value="${from}"></label><label>إلى<input id="report-end" type="date" value="${to}"></label><button id="run-report" class="primary">عرض التقرير</button></div><div id="report-result">${reportHTML(reportData||S.report)}</div>`+exportsBar('reports');
 } else if(page==='settings'){
 h=head(title,'إعدادات المنشأة المشتركة',openBtn('تعديل البيانات','property'))+table(['الحقل','القيمة'],[['المنشأة',esc(S.property.name)],['العنوان',esc(S.property.address)],['الرقم الضريبي',esc(S.property.tax_number)],['الضريبة الافتراضية',esc(S.property.tax_rate)+'%'],['العملة',esc(S.property.currency)],['نهاية التجربة / الاشتراك',esc(S.property.subscription_until||'غير محدد')],['المنطقة الزمنية','Asia/Riyadh'],['مصادر الحجز','استقبال، هاتف، Booking، Agoda، Airbnb، أخرى — إدخال يدوي'],['طرق الدفع','نقد، شبكة، تحويل']]);
 h+='<br><div class="card"><h2>إدارة الهيكل</h2><p>النوع والطابق والسعة والسعر الأساسي تضبط لكل وحدة من شاشة الوحدات.</p><a class="button" href="#units">إدارة الوحدات</a> <a class="button" href="#users">إدارة المستخدمين</a><p>النسخ الاحتياطي والاستعادة: راجع دليل التشغيل؛ النسخة تشمل قاعدة البيانات كاملة عبر أوامر الخادم.</p></div>';
 if(S.superuser)h+='<br>'+openBtn('تجديد الاشتراك','subscription')+' <a class="button" href="/setup/">إنشاء منشأة أخرى</a>';
 } else if(page==='users'){
 h=head(title,'الصلاحيات مفروضة على الخادم',openBtn('إضافة مستخدم','user'))+table(['المستخدم','الدور','الإجراء'],S.users.map(u=>[esc(u.user__username),tag(u.role),openBtn('تعديل الدور','membership',u.id)]));
 } else if(page==='audit'){
 h=head(title,'آخر 200 عملية؛ دون كلمات مرور أو بيانات اعتماد')+table(['الوقت','الموظف','العملية','المرجع'],S.audit.map(a=>[esc(a.created_at.slice(0,19)),esc(a.user__username),esc(a.action),esc(JSON.stringify(a.details))]));
 } else if(page==='profile'){
 h=head(title,'إدارة حسابك',openBtn('تغيير كلمة المرور','profile'))+`<div class="card"><h2>${esc(S.user)}</h2><p>الصلاحية: ${labels[S.role]}</p><p>المنشأة: ${esc(S.property.name)}</p></div>`;
 } else h=head('الصفحة غير موجودة','اختر إحدى الصفحات من القائمة');
 $('#page').innerHTML=h;updateExportLinks();
}
function field(name,label,type='text',value='',options=null,required=true){return `<label>${label}${options?`<select name="${name}" ${required?'required':''}>${options.map(([v,l])=>`<option value="${esc(v)}" ${String(v)===String(value)?'selected':''}>${esc(l)}</option>`).join('')}</select>`:`<input name="${name}" type="${type}" value="${esc(value)}" ${required?'required':''} ${type==='number'?'step="0.01" min="0"':''}>`}</label>`}
function unitOptions(){return S.units.filter(u=>u.active).map(u=>[u.id,u.number+' · '+u.kind])}
function resOptions(){return S.reservations.filter(r=>!['cancelled','no_show'].includes(r.status)).map(r=>[r.id,'#'+r.id+' · '+r.guest_name])}
function detail(r){
 let acts='';if(r.status==='confirmed')acts+=btn('تسجيل الوصول','checkin',{id:r.id})+openBtn('تعديل الحجز','edit',r.id)+btn('إلغاء الحجز','cancel',{id:r.id})+btn('لم يحضر','no_show',{id:r.id});
 if(['confirmed','checked_in'].includes(r.status))acts+=openBtn('تمديد','extend',r.id)+openBtn('إضافة خدمة','charge',r.id);
 if(r.status==='checked_in'){acts+=openBtn('نقل وحدة','move',r.id)+openBtn('مغادرة وتسوية','checkout',r.id);if(S.role==='owner')acts+=openBtn('تسوية مغادرة مبكرة','early_departure',r.id);}
 acts+=openBtn('تحصيل','payment',r.id)+openBtn('إصدار فاتورة','invoice',r.id);if(S.role==='owner')acts+=openBtn('رد مبلغ','refund',r.id)+openBtn('تصحيح فاتورة','adjustment',r.id);
 return `<div class="actions">${acts}</div><p>${esc(r.arrival)} ← ${esc(r.departure)} · ${tag(r.status)}</p><div class="detailmetrics">${[['الإجمالي',r.total],['الضريبة',r.tax],['صافي المدفوع',r.paid],['المتبقي',r.balance]].map(([n,v])=>`<div>${n}<strong>${money(v)}</strong></div>`).join('')}</div><div class="actions">${linkDoc('كشف الحساب','statement',r.id)}${r.status==='checked_out'?linkDoc('ملخص المغادرة','checkout',r.id):''}</div><h3>تخصيص الوحدات</h3>${table(['الوحدة','من','إلى'],r.allocations.map(a=>[esc(a.number),a.start,a.end]))}<h3>الرسوم</h3>${table(['البند','التاريخ','الصافي','الضريبة','الفاتورة'],r.charges.map(c=>[esc(c.description),c.date,money(c.net),money(c.tax),c.invoice||'غير مفوتر']))}<h3>الدفعات</h3>${table(['السند','المبلغ','الطريقة','المعاينة'],r.payments.map(p=>[p.id,money(p.amount),esc(p.method),linkDoc('فتح','receipt',p.id)]))}<h3>الفواتير والإشعارات</h3>${table(['المستند','النوع','المبلغ','المعاينة'],r.invoices.map(i=>[i.id,tag(i.kind),money(i.total),linkDoc('فتح','invoice',i.id)]))}`;
}
function openForm(form,id='',extra={}){
 const r=S.reservations.find(r=>r.id==id),u=S.units.find(u=>u.id==id),g=S.guests.find(g=>g.id==id);let f='',title='',action='',data={};modalTransform=null;
 const ff=field;
 if(form==='detail'){
 if(!r)return;$('#modal-title').textContent='الحجز #'+r.id+' · '+r.guest_name;$('#fields').innerHTML=detail(r);$('#save').hidden=true;modalAction=null;$('#form-error').textContent='';$('#modal').showModal();return;
 }
 if(form==='guest_detail'){
 if(!g)return;$('#modal-title').textContent=g.name;$('#fields').innerHTML=resTable(S.reservations.filter(r=>r.guest===g.id));$('#save').hidden=true;modalAction=null;$('#modal').showModal();return;
 }
 if(['booking','edit'].includes(form)){
 if(!S.guests.length){toast('أضف نزيلًا أولًا');openForm('guest');return}if(!S.units.some(u=>u.active)){toast('أضف وحدة أولًا');return}
 title=r?'تعديل الحجز':'حجز جديد';action=r?'reservation_edit':'reservation_create';data=r?{id:r.id}:{};
 f=ff('guest','النزيل','',r?.guest||'',S.guests.map(g=>[g.id,g.name]))+ff('unit','الوحدة','',r?.allocations.at(-1)?.unit||extra.unit||'',unitOptions())+ff('arrival','الوصول','date',r?.arrival||extra.date||S.today)+ff('departure','المغادرة','date',r?.departure||addDays(extra.date||S.today,1))+ff('persons','عدد النزلاء','number',r?.persons||1)+ff('rate','سعر الليلة قبل الضريبة','number',(r?.rate||S.units.find(u=>u.id==extra.unit)?.rate||S.units[0]?.rate||15000)/100)+ff('source','المصدر','',r?.source||'استقبال',[['استقبال','استقبال'],['هاتف','هاتف'],['Booking','Booking'],['Agoda','Agoda'],['Airbnb','Airbnb'],['أخرى','أخرى']]);
 } else if(form==='guest'){
 title=g?'تعديل النزيل':'إضافة نزيل';action='guest_save';data=g?{id:g.id}:{};f=ff('name','الاسم','text',g?.name)+ff('phone','الجوال','tel',g?.phone,null,false)+ff('email','البريد','email',g?.email,null,false);
 } else if(form==='unit'){
 title=u?'تعديل الوحدة':'إضافة وحدة';action='unit_save';data=u?{id:u.id}:{};f=ff('number','رقم الوحدة','text',u?.number)+ff('kind','نوع الوحدة','text',u?.kind||'استوديو')+ff('floor','الطابق','text',u?.floor||'الأرضي')+ff('capacity','السعة','number',u?.capacity||2)+ff('rate','سعر الليلة قبل الضريبة','number',(u?.rate||15000)/100)+ff('active','حالة الوحدة','',u?.active===false?'0':'1',[['1','نشطة'],['0','مؤرشفة']]);modalTransform=d=>({...d,active:d.active==='1'});
 } else if(['payment','refund','invoice','charge','extend','move','checkout','adjustment','early_departure'].includes(form)){
 if(!resOptions().length){toast('أنشئ حجزًا أولًا');return}data=r?{id:r.id}:{};if(!r)f+=ff('id','الحجز','',null,resOptions());
 action=form;title=({payment:'تسجيل دفعة',refund:'رد مبلغ للنزيل',invoice:'إصدار فاتورة تجريبية',charge:'إضافة خدمة',extend:'تمديد الإقامة',move:'نقل الوحدة',checkout:'مراجعة وتسوية المغادرة',adjustment:'تصحيح فاتورة',early_departure:'تسوية مغادرة مبكرة'})[form];
 if(['payment','refund'].includes(form))f+=ff('amount','المبلغ','number',form==='refund'?Math.max(0,-(r?.balance||0))/100:Math.max(0,r?.balance||0)/100)+ff('method','طريقة الدفع','',null,[['نقد','نقد'],['شبكة','شبكة'],['تحويل','تحويل']])+ff('reference','المرجع / سبب الرد','text','',null,false);
 if(form==='invoice')f+=ff('buyer','اسم المشتري / الشركة','text',r?.guest_name||'')+ff('buyer_tax','رقم المشتري الضريبي','text','',null,false)+ff('buyer_address','عنوان المشتري','text','',null,false);
 if(form==='charge')f+=ff('description','وصف الخدمة')+ff('amount','قبل الضريبة','number',0)+ff('date','تاريخ الخدمة','date',S.today);
 if(form==='extend')f+=ff('departure','المغادرة الجديدة','date',addDays(r?.departure||S.today,1))+ff('rate','سعر الليلة الإضافية قبل الضريبة','number',(r?.rate||15000)/100);
 if(form==='early_departure')f+=`<p>إلغاء الليالي من اليوم حتى موعد المغادرة الأصلي، وإصدار إشعارات للرسوم المفوترة. راجع الرصيد ورد الزيادة ثم أكمل المغادرة.</p>`+ff('departure','المغادرة الجديدة','date',S.today);
 if(form==='move')f+=ff('unit','الوحدة الجديدة','',null,unitOptions());
 if(form==='checkout'){f+=`<p>الإجمالي: ${money(r?.total)} · المقبوض: ${money(r?.paid)} · المتبقي: ${money(r?.balance)}</p><p>راجع المستندات والرسوم قبل تأكيد المغادرة. سيبقى أي رصيد معتمد مديونية واضحة.</p>`;if(S.role==='owner')f+=ff('allow_debt','اعتماد المغادرة بمديونية','',0,[['0','لا، يلزم تسوية الرصيد'],['1','نعم، اعتماد مديونية']]);modalTransform=d=>({...d,allow_debt:d.allow_debt==='1'});}
 if(form==='adjustment')f+=ff('invoice','الفاتورة الأصلية','',null,(r?.invoices||[]).filter(i=>i.kind==='invoice').map(i=>[i.id,'INV-'+i.id]))+ff('kind','نوع التصحيح','',null,[['credit','تخفيض / إشعار دائن'],['debit','زيادة / إشعار مدين']])+ff('amount','المبلغ شامل الضريبة','number',0)+ff('reason','سبب التصحيح');
 } else if(form==='block'){
 title='حجب وحدة للصيانة';action='block';f=ff('unit','الوحدة','',null,unitOptions())+ff('start','بداية الحجب','date',S.today)+ff('end','نهاية الحجب - غير مشمولة','date',addDays(S.today,1))+ff('reason','السبب');
 } else if(form==='property'){
 title='إعدادات المنشأة';action='property_save';f=ff('name','اسم المنشأة','text',S.property.name)+ff('address','العنوان','text',S.property.address,null,false)+ff('tax_number','الرقم الضريبي','text',S.property.tax_number,null,false)+ff('tax_rate','نسبة الضريبة %','number',S.property.tax_rate);
 } else if(form==='user'){
 title='مستخدم جديد';action='user_add';f=ff('username','اسم المستخدم')+ff('email','البريد لاستعادة الحساب','email','',null,false)+ff('password','كلمة المرور','password')+ff('role','الدور','',null,[['reception','استقبال'],['owner','مالك']]);
 } else if(form==='membership'){
 const m=S.users.find(u=>u.id==id);title='صلاحيات '+m.user__username;action='membership_save';data={id:m.id};f=ff('role','الدور','',m.role,[['reception','استقبال'],['owner','مالك']]);
 } else if(form==='profile'){
 title='تغيير كلمة المرور';action='profile';f=ff('old_password','كلمة المرور الحالية','password')+ff('password','كلمة المرور الجديدة','password');
 } else if(form==='subscription'){
 title='تجديد الاشتراك — مشغل النظام';action='subscription';f=ff('until','حتى تاريخ','date',addDays(S.today,30));
 } else return;
 modalAction={action,data};operationKey=crypto.randomUUID();$('#modal-title').textContent=title;$('#fields').innerHTML='<div class="formgrid">'+f+'</div>';$('#form-error').textContent='';$('#save').hidden=false;$('#save').textContent=form==='checkout'?'تأكيد المغادرة':'حفظ';$('#modal').showModal();
}
function updateExportLinks(){document.querySelectorAll('a.export').forEach(a=>{if(a.dataset.dataset==='reports'){const q=new URLSearchParams({start:$('#report-start')?.value||S.today,end:$('#report-end')?.value||addDays(S.today,1)});a.href=a.href.split('?')[0]+'?'+q}})}
document.addEventListener('click',async e=>{
 const el=e.target.closest('button,a');if(!el)return;
 if(el.dataset.open){e.preventDefault();if($('#modal').open)$('#modal').close();openForm(el.dataset.open,el.dataset.id,{unit:el.dataset.unit,date:el.dataset.date});}
 if(el.dataset.go)location.hash=el.dataset.go;
 if(el.hasAttribute('data-print'))window.print();
 if(el.dataset.action){if(!confirm('تأكيد تنفيذ العملية؟'))return;el.disabled=true;try{await mutate(el.dataset.action,JSON.parse(el.dataset.payload));await load();if($('#modal').open)$('#modal').close();toast('تم تنفيذ العملية')}catch(err){toast(err.message)}finally{el.disabled=false}}
 if(el.id==='run-report'){try{reportData=await request('/api/reports/?'+new URLSearchParams({start:$('#report-start').value,end:$('#report-end').value}));$('#report-result').innerHTML=reportHTML(reportData);updateExportLinks()}catch(err){toast(err.message)}}
});
$('#modalform').addEventListener('submit',async e=>{e.preventDefault();if(!modalAction)return;$('#save').disabled=true;let d={...Object.fromEntries(new FormData(e.target)),...modalAction.data};if(modalTransform)d=modalTransform(d);try{await mutate(modalAction.action,d,operationKey);$('#modal').close();await load();toast('تم الحفظ وتحديث الشاشات')}catch(err){$('#form-error').textContent=err.message}finally{$('#save').disabled=false}});
$('#close-modal').onclick=$('#cancel-modal').onclick=()=>$('#modal').close();
$('#menu').onclick=()=>$('#sidebar').classList.toggle('open');
$('#property').onchange=async e=>{try{await mutate('select_property',{id:e.target.value});reportData=null;search='';await load()}catch(err){toast(err.message)}};
document.addEventListener('input',e=>{if(e.target.id==='search'){const pos=e.target.selectionStart;search=e.target.value;render();$('#search')?.focus();$('#search')?.setSelectionRange(pos,pos)}});
document.addEventListener('change',e=>{if(e.target.id==='calendar-start'){calendarStart=e.target.value;render()}if(['report-start','report-end'].includes(e.target.id))updateExportLinks()});
window.addEventListener('hashchange',()=>{search='';reportData=null;$('#sidebar').classList.remove('open');render()});
load().catch(e=>{$('#page').textContent=e.message});
