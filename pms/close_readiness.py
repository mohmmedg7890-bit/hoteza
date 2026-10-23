"""Read-only, bounded review of ledger sources and closing-date reconciliations.
This report never locks a period, posts entries or certifies statutory closing.
"""
import hashlib,json
from datetime import date,timedelta
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import Property,LedgerOpening,LedgerReconciliation,Payment,Expense,Reservation
from .ledger import authorize,trial_balance
from .ledger_sources import preview
from .reconciliation import comparison,MONEY_ACCOUNTS
from .services import require,RuleError

LIMIT=200

@transaction.atomic
def review(user,prop_id,start,end):
    prop=Property.objects.select_for_update().get(pk=prop_id);authorize(user,prop.pk)
    require(date(1900,1,2)<=start<end and (end-start).days<=370 and end<=timezone.localdate()+timedelta(days=1),'اختر فترة حتى 370 يومًا دون أيام مستقبلية؛ النهاية غير مشمولة')
    blockers=[];sources=[];reconciliations=[]
    def block(code,message):blockers.append({'code':code,'message':message})
    opening=LedgerOpening.objects.filter(property=prop).first()
    if not opening:block('opening_missing','لم تعتمد الأرصدة الافتتاحية')
    elif start<opening.start_date:block('before_cutover','الفترة تبدأ قبل تاريخ بدء الدفتر؛ راجع الانتقال والأرصدة الافتتاحية')
    if opening and opening.unallocated_ack:block('unallocated_opening','توجد افتتاحيات عملاء مجمعة غير مخصصة؛ يلزم فحص تخصيصها يدويًا')
    if end>timezone.localdate():block('period_incomplete','الفترة تشمل اليوم الجاري؛ النتائج أولية حتى اكتمال اليوم')
    queries=[('payment',Payment.objects.filter(reservation__property=prop,created_at__date__gte=start,created_at__date__lt=end)),('expense',Expense.objects.filter(property=prop,created_at__date__gte=start,created_at__date__lt=end)),('reservation',Reservation.objects.filter(property=prop).filter(Q(charges__service_date__gte=start,charges__service_date__lt=end)|Q(payments__created_at__date__gte=start,payments__created_at__date__lt=end)|Q(checked_out_at__date__gte=start,checked_out_at__date__lt=end)).distinct())]
    count=sum(q.count() for _,q in queries)
    if count>LIMIT:block('scan_limit',f'عدد المصادر {count} يتجاوز حد الفحص {LIMIT}؛ ضيّق الفترة. التقرير غير مكتمل')
    remaining=LIMIT
    for kind,query in queries:
        ids=list(query.order_by('pk').values_list('pk',flat=True)[:remaining]);remaining-=len(ids)
        for pk in ids:
            row={'kind':kind,'id':pk,'new':0,'conflicts':0,'status':'reviewed','message':''}
            try:
                # Locks must not hide missing entries: inspection remains possible in locked days.
                plan=preview(user,prop.pk,kind,pk,check_locks=False)
                entries=[x for x in plan['entries'] if str(start)<=x['entry_date']<str(end)]
                row['new']=sum(x['status']=='new' for x in entries);row['conflicts']=sum(x['status']=='conflict' for x in entries)
                if row['new'] or row['conflicts']:
                    row['status']='pending';row['message']='قيود غير مرحّلة أو مصادر تغيرت بعد الترحيل'
            except RuleError as exc:
                row['status']='blocked';row['message']=str(exc)
            sources.append(row)
    if any(x['status']!='reviewed' for x in sources):block('sources_pending','توجد مصادر غير مرحّلة أو متغيرة أو تحتاج مراجعة؛ راجع تفاصيل المصادر')
    closing_day=end-timedelta(days=1)
    if opening and closing_day>=opening.start_date:
        for code in sorted(MONEY_ACCOUNTS):
            record=LedgerReconciliation.objects.filter(property=prop,account__code=code,date=closing_day).order_by('-created_at','-id').first()
            row={'account':code,'date':str(closing_day),'status':'missing','difference':None,'reference':''}
            if record:
                row['reference']=record.reference;row['difference']=record.difference
                try:
                    current=comparison(user,prop.pk,code,closing_day,record.actual_balance)
                    row['status']='stale' if current['digest']!=record.digest else 'difference' if record.difference else 'matched'
                except RuleError as exc:row['status']='blocked';row['message']=str(exc)
            reconciliations.append(row)
        if any(x['status']!='matched' for x in reconciliations):block('reconciliation_pending','يلزم محضر مطابق حديث للصندوق والبنك والبطاقات في آخر يوم من الفترة، حتى للحسابات ذات الرصيد الصفري')
    try:
        balance=trial_balance(user,prop.pk,start,end)
        if balance['debit']!=balance['credit'] or balance['closing_debit']!=balance['closing_credit']:block('unbalanced','ميزان الفترة غير متوازن')
    except RuleError as exc:balance=None;block('balance_unavailable',str(exc))
    result={'property':prop.pk,'start':str(start),'end':str(end),'currency':prop.currency,'opening_id':opening.pk if opening else None,'source_count':count,'scanned':len(sources),'complete_scan':count<=LIMIT,'sources':sources,'reconciliations':reconciliations,'blockers':blockers,'checks_passed':not blockers,'certified_close':False,'balance':balance,'notice':'فحص إرشادي للمصادر المدعومة فقط، وليس إقفالًا معتمدًا أو إثبات امتثال ضريبي. لا ينشئ قيودًا أو سندات ولا يقفل الفترة. النتائج تتغير عند تعديل التشغيل؛ أعد الفحص قبل المراجعة النهائية.'}
    result['digest']=hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return result
