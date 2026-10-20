"""All mutations go through one transactional, tenant-scoped boundary."""
import hashlib, json
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django.db import transaction
from django.db.models import Sum
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone
from .models import Property, Membership, Unit, Guest, Reservation, Allocation, Block, Charge, Payment, Invoice, Audit, Operation

class RuleError(Exception):
    pass

def require(ok, message):
    if not ok:
        raise RuleError(message)

def money(value, positive=True):
    try:
        v = Decimal(str(value))
        require(v.is_finite(), 'مبلغ غير صحيح')
        require(v.as_tuple().exponent >= -2, 'المبلغ لا يتجاوز منزلتين عشريتين')
        n = int((v*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
        require(abs(n) <= 10000000000, 'المبلغ أكبر من الحد المسموح')
        require(n >= 0 or not positive, 'المبلغ لا يكون سالبًا')
        return n
    except (InvalidOperation, ValueError, OverflowError):
        raise RuleError('مبلغ غير صحيح')

def day(value):
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise RuleError('تاريخ غير صحيح')

def text(data, key, maxlen=160, default=''):
    s = str(data.get(key, default)).strip()
    require(len(s) <= maxlen, f'الحقل {key} أطول من المسموح')
    return s

def owned(model, prop, pk):
    try:
        return model.objects.get(pk=int(pk),property=prop)
    except (ValueError, TypeError, model.DoesNotExist):
        raise RuleError('السجل غير موجود في منشأتك')

def balance(r):
    charges=list(r.charges.all()); payments=list(r.payments.all())
    net, tax = sum(c.net for c in charges),sum(c.tax for c in charges)
    paid = sum(p.amount for p in payments)
    return {'net':net,'tax':tax,'total':net+tax,'paid':paid,'balance':net+tax-paid}

def dates(start, end):
    require(start < end, 'المغادرة يجب أن تكون بعد الوصول')
    require((end-start).days <= 370, 'المدة القصوى 370 ليلة')
    return [start+timedelta(days=i) for i in range((end-start).days)]

def available(unit, start, end, persons=1, exclude=None):
    dates(start,end)
    require(unit.active, 'الوحدة مؤرشفة')
    require(0 < persons <= unit.capacity, 'سعة الوحدة غير كافية')
    q = Allocation.objects.filter(unit=unit,start__lt=end,end__gt=start).exclude(reservation__status__in=['cancelled','no_show'])
    if exclude:
        q = q.exclude(reservation=exclude)
    require(not q.exists(), 'الوحدة محجوزة في الفترة المطلوبة')
    # An overdue in-house guest still physically blocks the unit.
    overdue = Allocation.objects.filter(unit=unit,reservation__status='checked_in',reservation__departure__lte=timezone.localdate()).order_by('reservation_id','start')
    for a in overdue:
        if a.reservation_id != getattr(exclude,'id',None) and a == a.reservation.allocations.order_by('start','id').last():
            require(False, 'الوحدة مشغولة بنزيل متأخر عن المغادرة')
    require(not Block.objects.filter(unit=unit,start__lt=end,end__gt=start).exists(), 'الوحدة محجوبة للصيانة')

def add_charge(r, description, amount, service_date, kind='service'):
    tax = int((Decimal(amount)*r.property.tax_rate/100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    return Charge.objects.create(reservation=r,description=description,net=amount,tax=tax,service_date=service_date,kind=kind)

def nightly(r,start,end,rate):
    for d in dates(start,end):
        add_charge(r,'إقامة ليلة '+d.isoformat(),rate,d,'room')

def audit(prop,user,action,details):
    Audit.objects.create(property=prop,user=user,action=action,details=details)

def reverse_future_nights(r, cut):
    """Preserve billed lines and credit their unused nights; remove only draft charges."""
    future=list(r.charges.filter(kind='room',service_date__gte=cut))
    groups={}
    for c in future:
        if c.invoice_id:groups.setdefault(c.invoice_id,[]).append(c)
        else:c.delete()
    for invoice_id,charges in groups.items():
        ref=Invoice.objects.get(pk=invoice_id)
        require(not r.invoices.filter(reference=ref,kind='credit').exists(),'توجد تسويات سابقة على الفاتورة؛ راجع المغادرة المبكرة يدويًا')
        lines=[{'description':'إلغاء ليلة غير مستخدمة: '+str(c.service_date),'date':str(c.service_date),'net':-c.net,'tax':-c.tax} for c in charges]
        inv=Invoice.objects.create(reservation=r,kind='credit',reference=ref,total=sum(x['net']+x['tax'] for x in lines),snapshot={**ref.snapshot,'lines':lines})
        for x in lines:Charge.objects.create(reservation=r,service_date=day(x['date']),description=x['description'],net=x['net'],tax=x['tax'],kind='room_reversal',invoice=inv)

OWNER_ONLY = {'property_save','unit_save','user_add','membership_save','subscription','refund','adjustment','block_remove','early_departure'}

@transaction.atomic
def perform(user, prop_id, action, d, key):
    # Serialize all writes for a property. SQLite development uses BEGIN IMMEDIATE;
    # PostgreSQL workers share this row lock, including maintenance and reservations.
    prop = Property.objects.select_for_update().get(pk=prop_id)
    member = Membership.objects.filter(property=prop,user=user).first()
    require(member is not None, 'لا تملك صلاحية لهذه المنشأة')
    require(action not in OWNER_ONLY or member.role=='owner','هذه العملية للمالك فقط')
    digest = hashlib.sha256(json.dumps([user.pk,action,d],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    prior = Operation.objects.filter(property=prop,key=key).first()
    if prior:
        require(prior.digest==digest,'مفتاح العملية مستخدم لطلب مختلف')
        return prior.result
    require(prop.subscription_until is None or prop.subscription_until >= timezone.localdate() or action=='subscription','انتهت الفترة التجريبية؛ تواصل مع مشغل النظام للتجديد')
    result = {}
    if action == 'guest_save':
        g = owned(Guest,prop,d['id']) if d.get('id') else Guest(property=prop)
        g.name = text(d,'name'); require(bool(g.name),'اسم النزيل مطلوب')
        g.phone = text(d,'phone',40); g.email = text(d,'email',254)
        g.full_clean(); g.save(); result={'id':g.pk}
    elif action == 'unit_save':
        u = owned(Unit,prop,d['id']) if d.get('id') else Unit(property=prop)
        u.number=text(d,'number',30); u.kind=text(d,'kind',80); u.floor=text(d,'floor',40)
        require(bool(u.number and u.kind),'رقم الوحدة والنوع مطلوبان')
        u.capacity=int(d.get('capacity',2)); require(1<=u.capacity<=30,'السعة من 1 إلى 30')
        u.rate=money(d.get('rate',150)); u.active=bool(d.get('active',True))
        require(u.active or not u.allocation_set.filter(Q(reservation__status='checked_in')|Q(end__gt=timezone.localdate(),reservation__status='confirmed')).exists(),'للوحدة حجوزات قائمة؛ لا يمكن أرشفتها')
        u.full_clean(); u.save(); result={'id':u.pk}
    elif action == 'reservation_create':
        a,b=day(d.get('arrival')),day(d.get('departure')); dates(a,b)
        require(a>=timezone.localdate(),'الحجز الجديد لا يبدأ في الماضي')
        u=owned(Unit,prop,d.get('unit')); g=owned(Guest,prop,d.get('guest')); n=int(d.get('persons',1))
        available(u,a,b,n)
        r=Reservation.objects.create(property=prop,guest=g,arrival=a,departure=b,persons=n,rate=money(d.get('rate',u.rate/100)),source=text(d,'source',60,'استقبال'))
        Allocation.objects.create(reservation=r,unit=u,start=a,end=b); nightly(r,a,b,r.rate)
        result={'id':r.pk}
    elif action in {'reservation_edit','checkin','checkout','cancel','no_show','extend','move','payment','refund','charge','invoice','adjustment','early_departure'}:
        r=owned(Reservation,prop,d.get('id'))
        a=r.allocations.order_by('start','id').last()
        if action == 'reservation_edit':
            require(r.status=='confirmed','تعديل الفترة متاح للحجز المؤكد فقط')
            require(not r.invoices.exists() and not r.payments.exists(),'الحجز له مستندات مالية؛ استخدم التسوية بدل إعادة التسعير')
            start,end=day(d.get('arrival')),day(d.get('departure')); dates(start,end)
            require(start>=timezone.localdate(),'الوصول لا يبدأ في الماضي')
            u=owned(Unit,prop,d.get('unit')); n=int(d.get('persons',r.persons)); available(u,start,end,n,r)
            r.arrival=start;r.departure=end;r.persons=n;r.rate=money(d.get('rate',r.rate/100))
            if d.get('guest'):r.guest=owned(Guest,prop,d['guest'])
            r.source=text(d,'source',60,r.source);r.save()
            r.allocations.all().delete(); Allocation.objects.create(reservation=r,unit=u,start=start,end=end)
            r.charges.all().delete(); nightly(r,start,end,r.rate)
        elif action == 'checkin':
            require(r.status=='confirmed','الحجز غير مؤهل للتسكين')
            require(r.arrival<=timezone.localdate()<r.departure,'التسكين خلال فترة الإقامة فقط')
            available(a.unit,a.start,a.end,r.persons,r)
            require(a.unit.cleaning=='ready','الوحدة غير جاهزة للتسكين')
            r.status='checked_in';r.checked_in_at=timezone.now();r.save()
        elif action == 'checkout':
            require(r.status=='checked_in','الحجز غير مسكن')
            require(timezone.localdate()>=r.departure,'المغادرة المبكرة تتطلب تسوية الليالي أولًا بواسطة المالك')
            require(balance(r)['balance']==0 or (member.role=='owner' and d.get('allow_debt') and balance(r)['balance']>0),'يجب تسوية الحساب أو اعتماد مديونية من المالك')
            require(not r.charges.filter(invoice__isnull=True).exists(),'أصدر فاتورة الرسوم غير المفوترة قبل المغادرة')
            r.status='checked_out';r.checked_out_at=timezone.now();r.save()
            a.unit.cleaning='dirty';a.unit.save()
        elif action == 'early_departure':
            require(r.status=='checked_in','الحجز غير مسكن')
            cut=day(d.get('departure',timezone.localdate()))
            require(cut==timezone.localdate() and r.arrival<cut<r.departure,'المغادرة المبكرة من اليوم التالي للوصول وحتى قبل الموعد الأصلي')
            reverse_future_nights(r,cut)
            for alloc in r.allocations.filter(start__gte=cut):alloc.delete()
            r.allocations.filter(end__gt=cut).update(end=cut)
            r.departure=cut;r.save()
        elif action in {'cancel','no_show'}:
            require(r.status=='confirmed','الحجز غير مؤهل لهذه العملية')
            if action=='no_show':require(r.arrival<timezone.localdate(),'لم يحن إثبات عدم الحضور')
            if r.invoices.exists() or r.payments.exists():
                b=balance(r)
                require(member.role=='owner' and b['total']==0 and b['paid']==0,'يلزم تصحيح الفواتير ورد المبالغ أولًا حتى يصبح إجمالي الحساب وصافي المقبوض صفرًا')
            else:r.charges.all().delete()
            r.status='cancelled' if action=='cancel' else 'no_show';r.save()
        elif action == 'extend':
            require(r.status in ['confirmed','checked_in'],'لا يمكن تمديد هذا الحجز')
            end=day(d.get('departure'));require(end>r.departure,'موعد التمديد يجب أن يكون لاحقًا')
            available(a.unit,r.departure,end,r.persons,r)
            rate=money(d.get('rate',r.rate/100));nightly(r,r.departure,end,rate)
            a.end=end;a.save();r.departure=end;r.save()
        elif action == 'move':
            require(r.status=='checked_in','النقل متاح للمقيمين فقط')
            when=timezone.localdate();require(when<r.departure,'مدد الإقامة أولًا')
            u=owned(Unit,prop,d.get('unit'));require(u.pk!=a.unit_id,'اختر وحدة أخرى');available(u,when,r.departure,r.persons,r)
            require(u.cleaning=='ready','الوحدة الجديدة غير جاهزة')
            old=a.unit; end=a.end
            if a.start==when:a.delete()
            else:a.end=when;a.save()
            Allocation.objects.create(reservation=r,unit=u,start=when,end=end)
            old.cleaning='dirty';old.save()
            result={'from_unit':old.pk,'to_unit':u.pk,'moved_at':timezone.now().isoformat()}
        elif action in {'payment','refund'}:
            amount=money(d.get('amount'));require(amount>0,'المبلغ يجب أن يكون موجبًا')
            require(r.status not in ['cancelled','no_show'],'الحجز ملغى')
            if action=='refund':require(amount<=max(0,-balance(r)['balance']),'الرد لا يتجاوز الرصيد المستحق للنزيل');amount=-amount
            method=text(d,'method',30,'نقد');require(method in ['نقد','شبكة','تحويل'],'طريقة دفع غير صحيحة')
            p=Payment.objects.create(reservation=r,amount=amount,method=method,reference=text(d,'reference'),user=user);result={'payment':p.pk}
        elif action == 'charge':
            require(r.status in ['confirmed','checked_in'],'الحجز مغلق')
            desc=text(d,'description',200);require(bool(desc),'وصف الخدمة مطلوب')
            c=add_charge(r,desc,money(d.get('amount')),day(d.get('date',timezone.localdate())));result={'charge':c.pk}
        elif action == 'invoice':
            charges=list(r.charges.filter(invoice__isnull=True));require(bool(charges),'لا توجد رسوم غير مفوترة')
            require(all(c.net>=0 for c in charges),'التعديلات تحتاج مستند تصحيح')
            buyer=text(d,'buyer',200,r.guest.name); buyer_tax=text(d,'buyer_tax',30); buyer_address=text(d,'buyer_address',300)
            snap={'property':prop.name,'address':prop.address,'tax_number':prop.tax_number,'buyer':buyer,'buyer_tax':buyer_tax,'buyer_address':buyer_address,'guest':r.guest.name,'reservation':r.pk,'arrival':str(r.arrival),'departure':str(r.departure),'currency':prop.currency,'lines':[{'description':c.description,'date':str(c.service_date),'net':c.net,'tax':c.tax} for c in charges],'notice':'مستند تجريبي — غير صالح كفاتورة إلكترونية نظامية'}
            inv=Invoice.objects.create(reservation=r,snapshot=snap,total=sum(c.net+c.tax for c in charges));r.charges.filter(pk__in=[c.pk for c in charges]).update(invoice=inv);result={'invoice':inv.pk}
        elif action == 'adjustment':
            ref=r.invoices.filter(pk=d.get('invoice'),kind='invoice').first();require(ref is not None,'الفاتورة الأصلية مطلوبة')
            amount=money(d.get('amount'));require(amount>0,'المبلغ مطلوب')
            mode=d.get('kind');require(mode in ['credit','debit'],'نوع التصحيح غير صحيح')
            if mode=='credit':
                prev=-(r.invoices.filter(reference=ref,kind='credit').aggregate(n=Sum('total'))['n'] or 0)
                require(amount<=ref.total-prev,'التخفيض يتجاوز قيمة الفاتورة المتاحة')
            reason=text(d,'reason',200);require(bool(reason),'سبب التصحيح مطلوب')
            # amount is tax-inclusive; retain original invoice effective tax ratio.
            net_total=sum(x['net'] for x in ref.snapshot['lines']);tax_total=sum(x['tax'] for x in ref.snapshot['lines'])
            tax=int((Decimal(amount)*tax_total/ref.total).quantize(Decimal('1'),rounding=ROUND_HALF_UP)) if ref.total else 0
            sign=-1 if mode=='credit' else 1
            snap={**ref.snapshot,'lines':[{'description':reason,'date':str(timezone.localdate()),'net':sign*(amount-tax),'tax':sign*tax}]}
            inv=Invoice.objects.create(reservation=r,kind=mode,reference=ref,total=sign*amount,snapshot=snap)
            Charge.objects.create(reservation=r,service_date=timezone.localdate(),description=reason,net=sign*(amount-tax),tax=sign*tax,kind='adjustment',invoice=inv);result={'invoice':inv.pk}
        result['id']=r.pk
    elif action == 'cleaning':
        u=owned(Unit,prop,d.get('id'));state=d.get('cleaning');require(state in ['ready','dirty','cleaning'],'حالة غير صحيحة');u.cleaning=state;u.save()
    elif action == 'block':
        u=owned(Unit,prop,d.get('unit'));a,b=day(d.get('start')),day(d.get('end'));available(u,a,b)
        reason=text(d,'reason',250);require(bool(reason),'سبب الصيانة مطلوب');Block.objects.create(unit=u,start=a,end=b,reason=reason)
    elif action == 'block_remove':
        b=Block.objects.filter(pk=d.get('id'),unit__property=prop).first();require(b is not None,'السجل غير موجود');b.delete()
    elif action == 'property_save':
        prop.name=text(d,'name');prop.address=text(d,'address',300);prop.tax_number=text(d,'tax_number',30)
        require(bool(prop.name),'اسم المنشأة مطلوب')
        rate=Decimal(str(d.get('tax_rate',0)));require(rate.is_finite() and 0<=rate<=100,'نسبة ضريبة غير صحيحة');prop.tax_rate=rate;prop.full_clean();prop.save()
    elif action == 'user_add':
        username=text(d,'username',150);password=str(d.get('password',''));validate_password(password)
        require(not get_user_model().objects.filter(username=username).exists(),'اسم المستخدم مستخدم')
        role=d.get('role');require(role in ['owner','reception'],'دور غير صحيح')
        email=text(d,'email',254)
        from django.core.validators import validate_email
        if email:validate_email(email)
        u=get_user_model().objects.create_user(username=username,password=password,email=email);Membership.objects.create(property=prop,user=u,role=role)
    elif action == 'membership_save':
        m=Membership.objects.filter(property=prop,pk=d.get('id')).first();require(m is not None,'المستخدم غير موجود')
        require(m.user_id!=user.id,'لا تغيّر صلاحيتك من هذه الشاشة')
        role=d.get('role');require(role in ['owner','reception'],'دور غير صحيح');m.role=role;m.save()
    elif action == 'subscription':
        require(user.is_superuser,'تجديد الاشتراك لمشغل النظام فقط')
        prop.subscription_until=day(d.get('until'));prop.save()
    else:
        raise RuleError('عملية غير معروفة')
    # Never audit credentials or raw submitted payloads.
    audit(prop,user,action,{'result':result,'reason':text(d,'reason',250)})
    Operation.objects.create(property=prop,key=key,digest=digest,result=result)
    return result

def report(prop,start,end):
    days=dates(start,end); units=list(Unit.objects.filter(property=prop,active=True)); ids=[u.pk for u in units]
    allocations=list(Allocation.objects.filter(unit_id__in=ids,start__lt=end,end__gt=start).exclude(reservation__status__in=['cancelled','no_show']))
    blocks=list(Block.objects.filter(unit_id__in=ids,start__lt=end,end__gt=start))
    rows=[]
    per_unit={u.pk:{'number':u.number,'kind':u.kind,'capacity':0,'sold':0,'net':0,'tax':0} for u in units}
    per_source={}
    for d in days:
        blocked={b.unit_id for b in blocks if b.start<=d<b.end}
        occupied={a.unit_id for a in allocations if a.start<=d<a.end}
        charges=Charge.objects.filter(reservation__property=prop,service_date=d).aggregate(net=Sum('net'),tax=Sum('tax'))
        room_revenue=Charge.objects.filter(reservation__property=prop,service_date=d,kind__in=['room','room_reversal']).aggregate(n=Sum('net'))['n'] or 0
        paid=Payment.objects.filter(reservation__property=prop,created_at__date=d).aggregate(n=Sum('amount'))['n'] or 0
        rows.append({'date':str(d),'available':len(units)-len(blocked),'sold':len(occupied),'net':charges['net'] or 0,'tax':charges['tax'] or 0,'room_revenue':room_revenue,'paid':paid})
        for u in units:
            per_unit[u.pk]['capacity']+=int(u.pk not in blocked)
            per_unit[u.pk]['sold']+=int(u.pk in occupied)
        for a in allocations:
            if a.start<=d<a.end:
                src=a.reservation.source
                per_source.setdefault(src,{'source':src,'sold':0,'net':0,'tax':0})['sold']+=1
    for c in Charge.objects.filter(reservation__property=prop,service_date__gte=start,service_date__lt=end).select_related('reservation'):
        src=c.reservation.source
        per_source.setdefault(src,{'source':src,'sold':0,'net':0,'tax':0})
        per_source[src]['net']+=c.net;per_source[src]['tax']+=c.tax
        allocation=c.reservation.allocations.filter(start__lte=c.service_date,end__gt=c.service_date).first() or c.reservation.allocations.order_by('start','id').last()
        if allocation and allocation.unit_id in per_unit:
            per_unit[allocation.unit_id]['net']+=c.net;per_unit[allocation.unit_id]['tax']+=c.tax
    capacity=sum(x['available'] for x in rows);sold=sum(x['sold'] for x in rows);room=sum(x['room_revenue'] for x in rows)
    return {'rows':rows,'capacity':capacity,'sold':sold,'occupancy':round(100*sold/capacity,2) if capacity else 0,'net':sum(x['net'] for x in rows),'tax':sum(x['tax'] for x in rows),'paid':sum(x['paid'] for x in rows),'adr':round(room/sold) if sold else 0,'revpar':round(room/capacity) if capacity else 0,'by_unit':list(per_unit.values()),'by_source':list(per_source.values())}
