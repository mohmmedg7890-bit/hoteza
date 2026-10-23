"""Opening cutover, dated balance comparisons and explicit internal transfers.
A reconciliation records evidence and a difference; it never invents a balancing entry.
"""
from datetime import date,timedelta
import hashlib,json
from django.db import transaction
from django.db.models import Sum,Count,Max
from django.utils import timezone
from .models import Property,LedgerOpening,LedgerReconciliation,LedgerAccount,JournalEntry,JournalLine
from .ledger import authorize,normalize,post
from .services import require,RuleError

MONEY_ACCOUNTS={'1000','1010','1020'}

def valid_date(value):
    try:dt=date.fromisoformat(str(value))
    except ValueError:raise RuleError('تاريخ غير صحيح')
    require(date(1900,1,2)<=dt<=timezone.localdate(),'اختر تاريخًا من 1900-01-02 حتى اليوم');return dt

def reference(value):
    require(isinstance(value,str) and 3<=len(value.strip())<=160,'مرجع المستند من 3 إلى 160 حرفًا مطلوب');return value.strip()

def amount(value,signed=False):
    require(type(value) is int and abs(value)<=10**10 and (signed or value>=0),'المبلغ بوحدة العملة الصغرى ضمن الحد المسموح');return value

@transaction.atomic
def opening(user,prop_id,data):
    prop=Property.objects.select_for_update().get(pk=prop_id);authorize(user,prop.pk)
    require(not LedgerOpening.objects.filter(property=prop).exists(),'الأرصدة الافتتاحية معتمدة بالفعل؛ صحح بقيد مستقل ولا تكررها')
    require(not JournalEntry.objects.filter(property=prop).exists(),'يوجد دفتر مرحل بالفعل؛ يلزم انتقال ومطابقة مخصصان قبل اعتماد افتتاحيات')
    start=valid_date(data.get('date'));ref=reference(data.get('reference'));lines=data.get('lines')
    require(isinstance(lines,list),'بنود الافتتاح مطلوبة')
    if lines:
        normalized=normalize(prop,lines);seen=set()
        for x in normalized:
            require(x['account'].category in ['asset','liability','equity'],'الافتتاح هنا لحسابات الميزانية فقط؛ انقل نتائج الفترات السابقة إلى حقوق الملكية بعد مراجعتها')
            require(x['account'].code!='1000' or x['credit']==0,'لا يكون رصيد الصندوق الفعلي الافتتاحي سالبًا')
            pair=(x['account'].pk,x['reservation_id']);require(pair not in seen,'حساب وطرف افتتاحي مكرر');seen.add(pair)
            if x['account'].code in ['1100','2000','2010'] and x['reservation_id'] is None:
                require(data.get('allow_unallocated') is True,'حدد الحجز لحساب العميل أو أقر صراحة أن الرصيد مجمع وغير مخصص')
        e=post(user,prop.pk,source='opening:'+str(prop.pk),entry_date=start-timedelta(days=1),description='أرصدة افتتاحية: '+ref,lines=lines)
    else:
        require(data.get('confirm_zero') is True,'أقر صراحة أن جميع الأرصدة الافتتاحية صفر');e=None
    obj=LedgerOpening.objects.create(property=prop,start_date=start,reference=ref,entry=e,unallocated_ack=data.get('allow_unallocated') is True,user=user)
    return {'opening':obj.pk,'journal':e.pk if e else None,'start_date':str(start)}

def comparison(user,prop_id,code,dt,actual):
    authorize(user,prop_id);prop=Property.objects.get(pk=prop_id);day=valid_date(dt);actual=amount(actual,signed=True)
    require(code!='1000' or actual>=0,'رصيد الجرد النقدي الفعلي لا يكون سالبًا')
    require(code in MONEY_ACCOUNTS,'المطابقة للصندوق أو البنك أو مستحقات البطاقات فقط')
    account=LedgerAccount.objects.filter(property=prop,code=code).first();require(account is not None,'الحساب غير موجود في العقار')
    cut=LedgerOpening.objects.filter(property=prop).first();require(cut is not None,'اعتمد الأرصدة الافتتاحية قبل بدء المطابقات')
    require(day>=cut.start_date,'تاريخ المطابقة يسبق بدء الدفتر')
    require(not JournalEntry.objects.filter(property=prop).exclude(currency=prop.currency).exists(),'لا تجمع عملات مختلفة في المطابقة')
    totals=JournalLine.objects.filter(entry__property=prop,account=account,entry__date__lte=day).aggregate(d=Sum('debit'),c=Sum('credit'),n=Count('id'),last=Max('id'))
    book=(totals['d'] or 0)-(totals['c'] or 0)
    body={'property':prop.pk,'account':code,'date':str(day),'actual':actual,'book':book,'currency':prop.currency,'lines':totals['n'],'last_line':totals['last']}
    digest=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()
    return {**body,'difference':actual-book,'digest':digest,'status':'matched' if actual==book else 'difference','notice':'مقارنة بالقيود المعتمدة فقط. الفرق يبقى ظاهرًا؛ لا ينشأ قيد موازنة تلقائي، وهذه ليست عملية إقفال.'}

@transaction.atomic
def confirm(user,prop_id,data):
    prop=Property.objects.select_for_update().get(pk=prop_id);authorize(user,prop.pk)
    plan=comparison(user,prop.pk,data.get('account'),data.get('date'),data.get('actual'))
    require(data.get('digest')==plan['digest'],'تغير الرصيد أو البيانات بعد المعاينة؛ أعد المقارنة')
    ref=reference(data.get('reference'));explanation=data.get('explanation','')
    require(isinstance(explanation,str) and len(explanation.strip())<=250,'بيان المطابقة حتى 250 حرفًا')
    require(not plan['difference'] or len(explanation.strip())>=3,'وضح الفرق ومتابعته قبل حفظ محضر المطابقة')
    account=LedgerAccount.objects.get(property=prop,code=plan['account'])
    require(not LedgerReconciliation.objects.filter(property=prop,account=account,reference=ref).exists(),'مرجع المطابقة مستخدم لهذا الحساب')
    r=LedgerReconciliation.objects.create(property=prop,account=account,date=plan['date'],reference=ref,actual_balance=plan['actual'],book_balance=plan['book'],difference=plan['difference'],explanation=explanation.strip(),digest=plan['digest'],currency=prop.currency,user=user)
    return {'reconciliation':r.pk,'difference':r.difference}

@transaction.atomic
def transfer(user,prop_id,data):
    prop=Property.objects.select_for_update().get(pk=prop_id);authorize(user,prop.pk)
    source=data.get('from_account');dest=data.get('to_account');gross=amount(data.get('amount'));fee=amount(data.get('fee',0));dt=valid_date(data.get('date'));ref=reference(data.get('reference'))
    require(source in MONEY_ACCOUNTS and dest in MONEY_ACCOUNTS and source!=dest,'اختر حسابين ماليين مختلفين')
    require(gross>0 and 0<=fee<gross,'المبلغ موجب والرسوم أقل منه')
    source_key='transfer:'+hashlib.sha256(ref.encode()).hexdigest()
    lines=[{'account':source,'credit':gross},{'account':dest,'debit':gross-fee}]
    if fee:lines.append({'account':'5000','debit':fee})
    # A repeated reference is delegated to post()'s fingerprint check, even if funds moved already.
    previous=JournalEntry.objects.filter(property=prop,source=source_key).first()
    require(previous is None or not hasattr(previous,'reversal'),'مرجع التحويل سبق عكسه؛ استخدم مستندًا جديدًا بعد المراجعة')
    if previous is None:
        available=comparison(user,prop.pk,source,dt,0)['book'];require(available>=gross,'الرصيد الدفتري المرحل لا يكفي التحويل؛ طابق المصادر أولًا')
    e=post(user,prop.pk,source=source_key,entry_date=dt,description='تحويل / تسوية: '+ref,lines=lines)
    return {'journal':e.pk}

def state(user,prop_id,start,end):
    authorize(user,prop_id);o=LedgerOpening.objects.filter(property_id=prop_id).first()
    rows=[]
    for r in LedgerReconciliation.objects.filter(property_id=prop_id,date__gte=start,date__lt=end).select_related('account').order_by('-id')[:50]:
        current=comparison(user,prop_id,r.account.code,r.date,r.actual_balance)
        rows.append({'id':r.pk,'account':r.account.code,'date':str(r.date),'reference':r.reference,'actual':r.actual_balance,'book':r.book_balance,'difference':r.difference,'explanation':r.explanation,'stale':current['digest']!=r.digest})
    return {'opening':{'date':str(o.start_date),'reference':o.reference,'journal':o.entry_id,'unallocated':o.unallocated_ack} if o else None,'reconciliations':rows}
