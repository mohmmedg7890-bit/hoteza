"""Mandatory checkout review and atomic settlement, using existing vouchers/audit."""
import hashlib,json
from decimal import Decimal
from django.utils import timezone
from .models import Membership,Reservation
from .services import require,RuleError,balance,perform

def preview(user,prop_id,rid):
    member=Membership.objects.filter(property_id=prop_id,user=user).first();require(member is not None,'لا تملك صلاحية لهذه المنشأة')
    r=Reservation.objects.filter(property_id=prop_id,pk=rid).first();require(r is not None,'الحجز غير موجود في منشأتك')
    require(r.status=='checked_in','الحجز غير مسكن')
    today=timezone.localdate();b=balance(r)
    from datetime import timedelta
    same=today==r.arrival and r.departure==r.arrival+timedelta(days=1)
    blockers=[]
    if today<r.departure and not (same and member.role=='owner'):blockers.append('سوِّ الليالي غير المستخدمة من زر المغادرة المبكرة أولًا، ثم أعد فتح التسوية')
    if today>r.departure:blockers.append('مدد الإقامة حتى تاريخ اليوم أولًا لاحتساب الليالي المستحقة، ثم أعد فتح التسوية')
    body={'reservation':r.pk,'property':prop_id,'status':r.status,'arrival':str(r.arrival),'departure':str(r.departure),'today':str(today),'currency':r.property.currency,'balance':b,'same_day':same,'charges':list(r.charges.order_by('pk').values('id','net','tax','invoice_id','service_date','description')),'payments':list(r.payments.order_by('pk').values('id','amount','method','reference')),'allocations':list(r.allocations.order_by('pk').values('id','unit_id','start','end','rate'))}
    digest=hashlib.sha256(json.dumps(body,sort_keys=True,default=str,ensure_ascii=False).encode()).hexdigest()
    return {'reservation':r.pk,'digest':digest,**b,'arrival':str(r.arrival),'departure':str(r.departure),'nights':(r.departure-r.arrival).days,'same_day':same,'blockers':blockers,'can_refund':member.role=='owner','unbilled':sum(c.net+c.tax for c in r.charges.filter(invoice__isnull=True))}

def settle(user,prop,r,d,key):
    plan=preview(user,prop.pk,r.pk)
    require(d.get('settlement_ack') is True,'راجع التسوية وأقر بصحتها قبل حفظ المغادرة')
    require(d.get('settlement_digest')==plan['digest'],'تغير الحساب بعد المراجعة؛ أعد فتح التسوية قبل الحفظ')
    require(not plan['blockers'],'؛ '.join(plan['blockers']))
    mode=d.get('settlement_mode');amount=plan['balance'];voucher=None
    if amount==0:require(mode=='none','الرصيد صفر؛ اختر اعتماد حساب مسدد')
    elif amount>0 and mode=='debt':
        member=Membership.objects.get(user=user,property=prop)
        reason=d.get('debt_reason','')
        require(member.role=='owner' and isinstance(reason,str) and 10<=len(reason.strip())<=250,'اعتماد المديونية للمالك وبسبب موثق من 10 إلى 250 حرفًا')
    else:
        action='payment' if amount>0 else 'refund'
        require(mode==('collect' if amount>0 else 'refund'),'اختر تحصيل المتبقي أو رد الزيادة حسب رصيد الحساب')
        payload={'id':r.pk,'amount':str(Decimal(abs(amount))/100),'method':d.get('method'),'reference':d.get('reference','تسوية المغادرة')}
        voucher=perform(user,prop.pk,action,payload,hashlib.sha256((key+':settlement-voucher').encode()).hexdigest())['payment']
    require(balance(r)['balance']==0 or (mode=='debt' and amount>0),'لم تتم تسوية كامل الرصيد')
    return {'before':{k:plan[k] for k in ['net','tax','total','paid','balance','nights','arrival','departure']},'after':balance(r),'mode':mode,'voucher':voucher,'reason':d.get('debt_reason','') if mode=='debt' else '', 'digest':plan['digest']}
