"""Pricing, contracts and vouchers; shared by transactional reservation actions."""
from calendar import monthrange
from datetime import date,timedelta
from decimal import Decimal,ROUND_HALF_UP
from django.utils import timezone
from .models import Charge,Contract

OFFICIAL_PRESET={'name':'شركة سياح ايلان للشقق المخدومة','address':'خميس مشيط - حي المعارض','tax_number':'314251001600003','tax_rate':'15','commercial_registration':'7051771348','tourism_license':'10023501','phone':'+96617506111185','mobile':'+966570268833','postal_code':'62451','email':''}

def add_months(day,count):
    n=day.year*12+day.month-1+count
    return date(n//12,n%12+1,min(day.day,monthrange(n//12,n%12+1)[1]))

def price_on(r,when,rate):
    if r.rental_type!='monthly':return rate
    month=(when.year-r.arrival.year)*12+when.month-r.arrival.month
    if when<add_months(r.arrival,month):month-=1
    start=add_months(r.arrival,month);end=add_months(r.arrival,month+1)
    count=(end-start).days;offset=(when-start).days
    return rate//count+int(offset<rate%count)

def financial_parts(r):
    parts={'rent':0,'discount':0,'extras':0,'penalties':0}
    for c in r.charges.all():
        key='rent' if c.kind in ['room','room_reversal'] else 'discount' if c.kind in ['discount','discount_reversal'] else 'penalties' if c.kind=='penalty' else 'extras'
        parts[key]+=c.net
    return parts

def apply_discount(r,mode,value,require):
    require(not r.invoices.exists(),'الخصم بعد إصدار الفاتورة يحتاج إشعارًا دائنًا مرتبطًا بها')
    require(mode in ['fixed','percent'],'نوع الخصم غير صحيح')
    from .services import money
    room=list(r.charges.filter(kind='room'));base=sum(c.net for c in room)
    if mode=='percent':
        percent=Decimal(str(value));require(percent.is_finite() and 0<=percent<=100,'نسبة الخصم من صفر إلى 100')
        total=int((base*percent/100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    else:total=money(value)
    require(total<=base,'الخصم لا يتجاوز قيمة الإيجار قبل الضريبة')
    r.charges.filter(kind='discount',invoice__isnull=True).delete()
    remaining=total
    for i,c in enumerate(room):
        amount=remaining if i==len(room)-1 else total*c.net//base if base else 0
        remaining-=amount
        if amount:
            tax=int((Decimal(amount)*r.property.tax_rate/100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
            Charge.objects.create(reservation=r,unit=c.unit,service_date=c.service_date,kind='discount',description='خصم '+('نسبي '+str(value)+'%' if mode=='percent' else 'بمبلغ ثابت'),net=-amount,tax=-tax)

def issue_contract(r,user):
    from .services import balance
    prop=r.property;g=r.guest
    snapshot={'property':{'name':prop.name,'address':prop.address,'tax_number':prop.tax_number,'currency':prop.currency,'tax_rate':str(prop.tax_rate),**prop.official},'guest':{'name':g.name,'phone':g.phone,'email':g.email,**{k:g.profile.get(k,'') for k in ['nationality','id_type','id_number']}},'reservation':r.pk,'reference':f'RES-{prop.pk}-{r.pk:06}','arrival':str(r.arrival),'departure':str(r.departure),'arrival_time':r.arrival_time.strftime('%H:%M'),'departure_time':r.departure_time.strftime('%H:%M'),'rental_type':r.rental_type,'visit_purpose':r.visit_purpose,'source':r.source,'auto_extend':r.auto_extend,'units':[{'number':a.unit.number,'kind':a.unit.kind,'floor':a.unit.floor,'from':str(a.start),'to':str(a.end),'rate':a.rate if a.rate is not None else r.rate} for a in r.allocations.select_related('unit').all()],**balance(r),**financial_parts(r),'terms':list(prop.contract_terms),'terms_complete':len(prop.contract_terms)==14,'employee':user.username}
    return Contract.objects.create(reservation=r,snapshot=snapshot,user=user)
