"""Ledger posting locks only; not a PMS night audit or statutory closing."""
from datetime import date,timedelta
from django.db import transaction
from django.utils import timezone
from .models import Property,LedgerPeriodLock,LedgerPeriodReopen,LedgerOpening
from .ledger import authorize,trial_balance
from .services import require,RuleError

def active(prop):
    return LedgerPeriodLock.objects.filter(property=prop,reopening__isnull=True)

def writable(prop,dt):
    require(not active(prop).filter(start__lte=dt,end__gt=dt).exists(),'التاريخ داخل فترة دفتر مقفلة؛ أعد فتحها بسبب موثق أو استخدم تاريخ تصحيح مفتوح')

def bounds(d):
    try:start=date.fromisoformat(str(d.get('date')))
    except ValueError:raise RuleError('تاريخ الفترة غير صحيح')
    require(date(1900,1,2)<=start<timezone.localdate(),'اختر تاريخًا سابقًا صالحًا للفترة')
    kind=d.get('kind');require(kind in ['daily','monthly'],'اختر قفل يوم أو شهر')
    if kind=='monthly':
        require(start.day==1,'القفل الشهري يبدأ بأول يوم في الشهر')
        end=date(start.year+int(start.month==12),start.month%12+1,1)
    else:end=start+timedelta(days=1)
    require(end<=timezone.localdate(),'يمكن قفل أيام أو أشهر مكتملة فقط')
    return start,end,kind

def reason(d):
    value=d.get('reason');require(isinstance(value,str) and 10<=len(value.strip())<=250,'اكتب سببًا واضحًا من 10 إلى 250 حرفًا');return value.strip()

@transaction.atomic
def lock(user,prop_id,d):
    prop=Property.objects.select_for_update().get(pk=prop_id);authorize(user,prop.pk)
    start,end,kind=bounds(d);why=reason(d)
    opening=LedgerOpening.objects.filter(property=prop).first()
    require(opening is not None and start>=opening.start_date,'اعتمد الافتتاحية أولًا واختر فترة بعد بدء الدفتر')
    require(d.get('acknowledge_scope') is True,'أكد أن القفل للدفتر فقط وليس اعتمادًا لاكتمال العمليات أو المطابقات')
    require(not active(prop).filter(start__lt=end,end__gt=start).exists(),'الفترة تتداخل مع قفل قائم؛ أعد فتح الأقفال المتداخلة أولًا')
    snapshot=trial_balance(user,prop.pk,start,end)
    require(snapshot['debit']==snapshot['credit'] and snapshot['closing_debit']==snapshot['closing_credit'],'ميزان الفترة غير متوازن')
    item=LedgerPeriodLock.objects.create(property=prop,start=start,end=end,kind=kind,reason=why,snapshot=snapshot,user=user)
    return {'lock':item.pk}

@transaction.atomic
def reopen(user,prop_id,d):
    prop=Property.objects.select_for_update().get(pk=prop_id);authorize(user,prop.pk)
    item=active(prop).filter(pk=d.get('id')).first();require(item is not None,'القفل غير موجود أو أعيد فتحه')
    event=LedgerPeriodReopen.objects.create(lock=item,reason=reason(d),user=user)
    return {'reopening':event.pk,'lock':item.pk}

def state(user,prop_id):
    authorize(user,prop_id)
    return [{'id':x.pk,'start':str(x.start),'end':str(x.end),'kind':x.kind,'reason':x.reason,'active':not hasattr(x,'reopening'),'reopen_reason':x.reopening.reason if hasattr(x,'reopening') else ''} for x in LedgerPeriodLock.objects.filter(property_id=prop_id).select_related('reopening').order_by('-id')[:100]]
