"""Explicit owner-authorized ledger foundation. No automatic historical posting.
Amounts are integer minor currency units. Existing PMS reports are NOT ledger reports.
Writes must use post()/reverse(); direct SQL is outside the application boundary.
"""
import hashlib,json
from datetime import date
from django.db import transaction
from django.db.models import Max,Sum
from django.utils import timezone
from .models import Property,Membership,LedgerAccount,JournalEntry,JournalLine,Reservation,LedgerOpening
from .services import RuleError,require

CHART=[('1000','الصندوق','asset'),('1010','البنك','asset'),('1020','مستحقات البطاقات','asset'),('1100','ذمم العملاء','asset'),('2000','دفعات العملاء المقدمة','liability'),('2010','تأمينات العملاء','liability'),('2100','ضريبة مستحقة','liability'),('3000','حقوق الملكية الافتتاحية','equity'),('4000','إيراد الإقامة','revenue'),('4010','إيراد الخدمات','revenue'),('5000','مصروفات تشغيلية','expense')]

def authorize(user,prop_id):
    require(Membership.objects.filter(user=user,property_id=prop_id,role='owner').exists(),'دفتر الأستاذ متاح للمالك فقط حاليًا')

def normalize(prop,lines):
    require(isinstance(lines,list) and 2<=len(lines)<=100,'القيد من بندين إلى 100 بند')
    normalized=[]
    for x in lines:
        require(isinstance(x,dict),'صيغة بند غير صحيحة')
        code=x.get('account');require(isinstance(code,str) and len(code)<=16,'رمز الحساب مطلوب')
        debit=x.get('debit',0);credit=x.get('credit',0)
        require(type(debit) is int and type(credit) is int and 0<=debit<=10**10 and 0<=credit<=10**10,'المبالغ أعداد صحيحة بوحدة العملة الصغرى ضمن الحد المسموح')
        require((debit>0 and credit==0) or (credit>0 and debit==0),'كل بند مدين أو دائن فقط')
        account=LedgerAccount.objects.filter(property=prop,code=code).first();require(account is not None,'الحساب غير موجود في العقار')
        reservation=x.get('reservation')
        if reservation is not None:
            require(type(reservation) is int and Reservation.objects.filter(property=prop,pk=reservation).exists(),'الحجز غير موجود في العقار')
        normalized.append({'account':account,'debit':debit,'credit':credit,'reservation_id':reservation})
    require(sum(x['debit'] for x in normalized)==sum(x['credit'] for x in normalized),'القيد غير متوازن')
    return normalized

@transaction.atomic
def init_chart(user,prop_id):
    prop=Property.objects.select_for_update().get(pk=prop_id);authorize(user,prop.pk)
    for code,name,category in CHART:LedgerAccount.objects.get_or_create(property=prop,code=code,defaults={'name':name,'category':category})
    return LedgerAccount.objects.filter(property=prop).count()

@transaction.atomic
def post(user,prop_id,*,source,entry_date,description,lines,reversal_of=None):
    prop=Property.objects.select_for_update().get(pk=prop_id);authorize(user,prop.pk)
    require(isinstance(source,str) and 1<=len(source.strip())<=120,'مرجع المصدر مطلوب')
    require(isinstance(description,str) and 3<=len(description.strip())<=250,'بيان القيد مطلوب')
    try:dt=date.fromisoformat(str(entry_date))
    except ValueError:raise RuleError('تاريخ القيد غير صحيح')
    require(dt<=timezone.localdate(),'لا تنشر قيدًا مستقبليًا؛ تحقق من استحقاق الإيراد أولًا')
    require(not JournalEntry.objects.filter(property=prop).exclude(currency=prop.currency).exists(),'عملة العقار تغيرت؛ راجع ترحيل العملة قبل نشر قيود جديدة')
    cut=LedgerOpening.objects.filter(property=prop).first()
    require(cut is None or dt>=cut.start_date,'القيد يسبق تاريخ بدء الدفتر؛ منعًا لتكرار الأرصدة الافتتاحية')
    normalized=normalize(prop,lines)
    if reversal_of:
        require(reversal_of.property_id==prop.pk,'قيد العكس خارج العقار')
        expected=[(x.account_id,x.credit,x.debit,x.reservation_id) for x in reversal_of.lines.order_by('id')]
        require(expected==[(x['account'].pk,x['debit'],x['credit'],x['reservation_id']) for x in normalized],'العكس يجب أن يعكس بنود الأصل بالكامل')
        require(dt>=reversal_of.date,'العكس لا يسبق الأصل')
    fingerprint={'date':str(dt),'description':description.strip(),'currency':prop.currency,'reversal_of':getattr(reversal_of,'pk',None),'lines':[{**x,'account':x['account'].code} for x in normalized]}
    digest=hashlib.sha256(json.dumps(fingerprint,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    prior=JournalEntry.objects.filter(property=prop,source=source.strip()).first()
    if prior:
        require(prior.digest==digest,'مرجع المصدر مستخدم لقيد مختلف');return prior
    sequence=(JournalEntry.objects.filter(property=prop).aggregate(n=Max('sequence'))['n'] or 0)+1
    total=sum(x['debit'] for x in normalized)
    entry=JournalEntry.objects.create(property=prop,sequence=sequence,date=dt,description=description.strip(),source=source.strip(),digest=digest,currency=prop.currency,debit_total=total,credit_total=total,reversal_of=reversal_of,user=user)
    JournalLine.objects.bulk_create([JournalLine(entry=entry,**x) for x in normalized])
    return entry

@transaction.atomic
def reverse(user,prop_id,entry_id,entry_date,reason):
    prop=Property.objects.select_for_update().get(pk=prop_id);authorize(user,prop.pk)
    original=JournalEntry.objects.filter(property=prop,pk=entry_id).first();require(original is not None,'القيد غير موجود في العقار')
    require(not LedgerOpening.objects.filter(entry=original).exists(),'الافتتاحية ثابتة؛ استخدم قيد تصحيح مستقل بعد تاريخ البدء')
    require(original.reversal_of_id is None,'لا تعكس قيد عكس؛ استخدم قيد تصحيح مستقل')
    return post(user,prop.pk,source='reversal:'+str(original.pk),entry_date=entry_date,description=reason,lines=[{'account':x.account.code,'debit':x.credit,'credit':x.debit,'reservation':x.reservation_id} for x in original.lines.select_related('account').order_by('id')],reversal_of=original)

def trial_balance(user,prop_id,start,end):
    authorize(user,prop_id);require(start<end and (end-start).days<=370,'فترة الميزان من يوم إلى 370 يومًا ونهايتها غير مشمولة')
    require(not JournalEntry.objects.filter(property_id=prop_id).exclude(currency=Property.objects.get(pk=prop_id).currency).exists(),'عملة الدفتر مختلفة عن إعداد العقار؛ لا تجمع عملات مختلفة')
    rows=[]
    for a in LedgerAccount.objects.filter(property_id=prop_id).order_by('code'):
        base=JournalLine.objects.filter(account=a,entry__property_id=prop_id)
        opening=base.filter(entry__date__lt=start).aggregate(d=Sum('debit'),c=Sum('credit'))
        movement=base.filter(entry__date__gte=start,entry__date__lt=end).aggregate(d=Sum('debit'),c=Sum('credit'))
        op=(opening['d'] or 0)-(opening['c'] or 0);dr=movement['d'] or 0;cr=movement['c'] or 0;closing=op+dr-cr
        rows.append({'code':a.code,'name':a.name,'category':a.category,'opening':op,'debit':dr,'credit':cr,'closing_debit':max(closing,0),'closing_credit':max(-closing,0)})
    return {'start':str(start),'end':str(end),'currency':Property.objects.get(pk=prop_id).currency,'rows':rows,'debit':sum(x['debit'] for x in rows),'credit':sum(x['credit'] for x in rows),'closing_debit':sum(x['closing_debit'] for x in rows),'closing_credit':sum(x['closing_credit'] for x in rows),'notice':'دفتر تأسيسي؛ لم ترحل العمليات تلقائيًا. يشمل القيود اليدوية والمصادر المعتمدة فقط، وليس ميزانًا شاملًا للمنشأة.'}
