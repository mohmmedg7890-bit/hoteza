"""Reviewed trial posting adapters; no automatic production/historical migration.
Source charges carry the configured tax amounts. This is not a tax-point engine.
"""
from collections import defaultdict
from datetime import date
import hashlib,json
from django.db import transaction
from django.utils import timezone
from .models import Property,Payment,Expense,Reservation,JournalEntry
from .ledger import authorize,normalize,post
from .services import require,RuleError

CASH={'نقد':'1000','تحويل':'1010','شبكة':'1020'}

def line(account,amount,reservation=None):
    # Signed amount: positive is debit; negative is credit.
    return {'account':account,'debit':max(amount,0),'credit':max(-amount,0),'reservation':reservation}

def entry(source,dt,description,lines):
    lines=[x for x in lines if x['debit'] or x['credit']]
    if not lines:return None
    return {'source':source,'entry_date':str(dt),'description':description,'lines':lines}

def receipt(p):
    require(p.method in CASH,'طريقة سند القبض غير مدعومة محاسبيًا')
    return entry('payment:'+str(p.pk),timezone.localdate(p.created_at),'سند '+('قبض' if p.amount>0 else 'استرداد')+' PAY-'+str(p.pk),[line(CASH[p.method],p.amount,p.reservation_id),line('2000',-p.amount,p.reservation_id)])

def _owned(model,prop,pk):
    try:obj=model.objects.get(pk=int(pk))
    except (ValueError,TypeError,model.DoesNotExist):raise RuleError('المصدر غير موجود في العقار')
    owner=obj.reservation.property_id if model is Payment else obj.property_id
    require(owner==prop.pk,'المصدر غير موجود في العقار');return obj

def _raw(prop,kind,pk):
    if kind=='payment':return [receipt(_owned(Payment,prop,pk))]
    if kind=='expense':
        x=_owned(Expense,prop,pk);require(x.method in CASH,'طريقة سند الصرف غير مدعومة محاسبيًا')
        return [entry('expense:'+str(x.pk),timezone.localdate(x.created_at),'سند صرف EXP-'+str(x.pk),[line('5000',x.amount,x.reservation_id),line(CASH[x.method],-x.amount,x.reservation_id)])]
    require(kind=='reservation','نوع المصدر غير مدعوم')
    r=_owned(Reservation,prop,pk)
    require(r.status=='checked_out' and r.checked_out_at is not None,'ترحيل الإقامة متاح بعد تسجيل الخروج فقط؛ لا تعد رسوم الليالي المستقبلية إيرادًا مكتسبًا')
    charges=list(r.charges.order_by('service_date','id'));require(all(c.invoice_id for c in charges),'هناك رسوم غير مفوترة؛ راجع المستندات أولًا')
    payments=list(r.payments.order_by('created_at','id'))
    require(len(charges)+len(payments)<=2000,'قسّم المراجعة؛ المصدر أكبر من حد الترحيل الحالي')
    by_date=defaultdict(lambda:defaultdict(int));payments_by_date=defaultdict(int);plans=[]
    for c in charges:
        account='4000' if c.kind in ['room','room_reversal','discount','discount_reversal'] else '4010'
        by_date[c.service_date][account]+=c.net;by_date[c.service_date]['2100']+=c.tax
    for p in payments:
        plans.append(receipt(p));payments_by_date[timezone.localdate(p.created_at)]+=p.amount
    earned=paid=allocated=0
    for dt in sorted(set(by_date)|set(payments_by_date)):
        amounts=by_date[dt];gross=sum(amounts.values());earned+=gross;paid+=payments_by_date[dt]
        require(earned>=0 and paid>=0,'الرصيد التاريخي سالب؛ راجع تواريخ القيود والتصحيحات قبل الترحيل')
        if gross or any(amounts.values()):
            require(dt<=timezone.localdate(r.checked_out_at),'يوجد إيراد غير معكوس بعد الخروج؛ راجع المغادرة المبكرة')
            plans.append(entry(f'reservation:{r.pk}:charges:{dt}',dt,f'رسوم إقامة RES-{r.pk} / {dt}',[line('1100',gross,r.pk)]+[line(a,-v,r.pk) for a,v in sorted(amounts.items())]))
        desired=min(earned,paid);delta=desired-allocated
        if delta:
            plans.append(entry(f'reservation:{r.pk}:allocation:{dt}',dt,f'تخصيص مقدمات RES-{r.pk} / {dt}',[line('2000',delta,r.pk),line('1100',-delta,r.pk)]));allocated=desired
    return [x for x in plans if x]

def preview(user,prop_id,kind,pk):
    authorize(user,prop_id);prop=Property.objects.get(pk=prop_id)
    plans=_raw(prop,kind,pk)
    require(len(plans)<=500,'المصدر ينتج أكثر من 500 قيد؛ يلزم تقسيم الفترة')
    for plan in plans:
        require(date.fromisoformat(plan['entry_date'])<=timezone.localdate(),'المصدر يتضمن تاريخًا مستقبليًا')
        normalize(prop,plan['lines'])
        previous=JournalEntry.objects.filter(property=prop,source=plan['source']).prefetch_related('lines__account').first()
        plan['status']='new';plan['journal']=None
        if previous:
            current=[{'account':l.account.code,'debit':l.debit,'credit':l.credit,'reservation':l.reservation_id} for l in previous.lines.order_by('id')]
            same=current==plan['lines'] and str(previous.date)==plan['entry_date'] and previous.description==plan['description'] and previous.currency==prop.currency
            plan['journal']=previous.pk
            plan['status']='existing' if same and not hasattr(previous,'reversal') else 'conflict'
    body={'property':prop.pk,'currency':prop.currency,'kind':kind,'id':str(pk),'entries':sorted(plans,key=lambda p:(p['entry_date'],p['source']))}
    digest=hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return {**body,'digest':digest,'new':sum(x['status']=='new' for x in plans),'conflicts':sum(x['status']=='conflict' for x in plans),'notice':'ترحيل داخلي تجريبي حسب تاريخ الخدمة وتاريخ السند. القبض مقدمات حتى تخصيصه، والبطاقات مستحقات حتى التسوية. ليست معالجة ضريبية معتمدة أو إقفالًا شاملًا.'}

@transaction.atomic
def apply(user,prop_id,kind,pk,expected_digest):
    prop=Property.objects.select_for_update().get(pk=prop_id);authorize(user,prop.pk)
    plan=preview(user,prop.pk,kind,pk)
    require(isinstance(expected_digest,str) and expected_digest==plan['digest'],'تغيرت البيانات بعد المعاينة؛ أعد المعاينة قبل الاعتماد')
    require(not plan['conflicts'],'مصدر سبق ترحيله تغير أو عُكس؛ يلزم تصحيح ومطابقة يدويان، ولن تعدل القيود السابقة')
    ids=[]
    for p in plan['entries']:
        if p['status']=='existing':ids.append(p['journal']);continue
        ids.append(post(user,prop.pk,source=p['source'],entry_date=p['entry_date'],description=p['description'],lines=p['lines']).pk)
    return {'journals':ids,'created':plan['new'],'source_kind':kind,'source_id':str(pk)}
