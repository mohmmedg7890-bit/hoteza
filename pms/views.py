import json, hashlib
from datetime import timedelta
from decimal import InvalidOperation
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, transaction
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET
from .models import Property, Membership, Unit, Guest, Reservation, Block, Invoice, Payment, Audit, Expense, Contract
from .services import perform, balance, report, day, RuleError

@require_GET
def landing(request):
    return render(request,'landing.html')

def login_view(request):
    error=''
    if request.method=='POST':
        username=request.POST.get('username','')[:150]
        key='login:'+hashlib.sha256((request.META.get('REMOTE_ADDR','')+username).encode()).hexdigest()
        if cache.get(key,0)>=8:error='محاولات كثيرة؛ انتظر 15 دقيقة ثم حاول مجددًا'
        else:
            user=authenticate(request,username=username,password=request.POST.get('password',''))
            if user:
                cache.delete(key);login(request,user);return redirect('/app/')
            cache.set(key,cache.get(key,0)+1,900);error='بيانات الدخول غير صحيحة'
    return render(request,'login.html',{'error':error})

@require_POST
def logout_view(request):
    logout(request);return redirect('/login/')

@login_required
def app(request):
    memberships=Membership.objects.filter(user=request.user).select_related('property')
    if not memberships.exists():return redirect('/setup/')
    return render(request,'app.html',{'memberships':memberships})

@login_required
def setup(request):
    if Membership.objects.filter(user=request.user).exists() and not request.user.is_superuser:return redirect('/app/')
    error=''
    if request.method=='POST':
        name=request.POST.get('name','').strip()[:160]
        if not name:error='اسم المنشأة مطلوب'
        else:
            with transaction.atomic():
                p=Property.objects.create(name=name,subscription_until=timezone.localdate()+timedelta(days=30))
                Membership.objects.create(property=p,user=request.user,role='owner')
            request.session['property']=p.pk;return redirect('/app/')
    return render(request,'setup.html',{'error':error})

def membership(request):
    if not request.user.is_authenticated:raise RuleError('يجب تسجيل الدخول')
    qs=Membership.objects.filter(user=request.user).select_related('property')
    prop_id=request.session.get('property')
    m=qs.filter(property_id=prop_id).first() if prop_id else qs.first()
    if not m:raise RuleError('المنشأة غير متاحة لهذا الحساب')
    return m

def api_errors(fn):
    def wrapped(request,*a,**kw):
        if not request.user.is_authenticated:return JsonResponse({'error':'يجب تسجيل الدخول'},status=401)
        try:return fn(request,*a,**kw)
        except RuleError as e:return JsonResponse({'error':str(e)},status=400)
        except ValidationError as e:return JsonResponse({'error':'؛ '.join(e.messages)},status=400)
        except (ValueError,TypeError,KeyError,InvalidOperation,json.JSONDecodeError):return JsonResponse({'error':'راجع الحقول المطلوبة وصيغتها'},status=400)
        except IntegrityError:return JsonResponse({'error':'تعارض في البيانات؛ ربما الرقم مستخدم مسبقًا'},status=409)
        except OperationalError:return JsonResponse({'error':'البيانات مشغولة مؤقتًا؛ أعد الطلب بمفتاح العملية نفسه'},status=409)
    return wrapped

@require_GET
@api_errors
def state(request):
    m=membership(request);p=m.property;today=timezone.localdate()
    reservations=[]
    for r in Reservation.objects.filter(property=p).select_related('guest').prefetch_related('allocations__unit','charges','payments','invoices').order_by('-id'):
        allocations=[{'id':a.pk,'unit':a.unit_id,'number':a.unit.number,'kind':a.unit.kind,'floor':a.unit.floor,'rate':a.rate if a.rate is not None else r.rate,'start':str(a.start),'end':str(a.end)} for a in r.allocations.all()]
        reservations.append({'id':r.pk,'guest':r.guest_id,'guest_name':r.guest.name,'phone':r.guest.phone,'arrival':str(r.arrival),'departure':str(r.departure),'arrival_time':r.arrival_time.strftime('%H:%M'),'departure_time':r.departure_time.strftime('%H:%M'),'persons':r.persons,'rate':r.rate,'status':r.status,'source':r.source,'rental_type':r.rental_type,'visit_purpose':r.visit_purpose,'auto_extend':r.auto_extend,'reference':f'RES-{p.pk}-{r.pk:06}','contract':r.contracts.order_by('-id').values_list('id',flat=True).first(),'checked_in_at':r.checked_in_at,'checked_out_at':r.checked_out_at,'parts':__import__('pms.operations',fromlist=['financial_parts']).financial_parts(r),'allocations':allocations,**balance(r),'charges':[{'id':c.pk,'date':str(c.service_date),'description':c.description,'net':c.net,'tax':c.tax,'invoice':c.invoice_id} for c in r.charges.all()],'payments':[{'id':x.pk,'amount':x.amount,'method':x.method,'reference':x.reference,'user':x.user.username,'date':timezone.localtime(x.created_at).isoformat()} for x in r.payments.all()],'invoices':[{'id':i.pk,'kind':i.kind,'total':i.total,'reference':i.reference_id,'date':str(i.created_at.date())} for i in r.invoices.all()]})
    return JsonResponse({'today':str(today),'user':request.user.username,'superuser':request.user.is_superuser,'role':m.role,'property':{'id':p.pk,'name':p.name,'address':p.address,'tax_number':p.tax_number,'official':p.official,'contract_terms':p.contract_terms,'tax_rate':str(p.tax_rate),'currency':p.currency,'subscription_until':str(p.subscription_until or '')},'units':list(Unit.objects.filter(property=p).values()),'guests':[{**{f.name:getattr(g,f.name) for f in Guest._meta.fields if f.name not in ['photo','property','profile']},**g.profile,'has_photo':bool(g.photo)} for g in Guest.objects.filter(property=p)],'reservations':reservations,'expenses':list(Expense.objects.filter(property=p).values('id','reservation_id','amount','method','beneficiary','description','created_at','user__username')),'blocks':list(Block.objects.filter(unit__property=p).values()),'users':list(Membership.objects.filter(property=p).values('id','user__username','role')) if m.role=='owner' else [],'audit':list(Audit.objects.filter(property=p).order_by('-id').values('id','user__username','action','details','created_at')[:200]) if m.role=='owner' else [],'report':report(p,today,today+timedelta(days=1))})

@require_POST
@api_errors
def action(request,name):
    require_length=len(request.body)<=(300000 if name=='guest_save' else 60000 if name=='terms_save' else 20000)
    if not require_length:raise RuleError('الطلب أكبر من المسموح')
    data=json.loads(request.body)
    if not isinstance(data,dict):raise RuleError('صيغة طلب غير صحيحة')
    if name=='select_property':
        if not Membership.objects.filter(user=request.user,property_id=data.get('id')).exists():raise RuleError('المنشأة غير متاحة')
        request.session['property']=int(data['id']);return JsonResponse({'ok':True})
    if name=='profile':
        form=PasswordChangeForm(request.user,data={'old_password':data.get('old_password'),'new_password1':data.get('password'),'new_password2':data.get('password')})
        if not form.is_valid():raise RuleError('؛ '.join(str(x) for v in form.errors.values() for x in v))
        user=form.save();update_session_auth_hash(request,user);return JsonResponse({'ok':True})
    m=membership(request);key=request.headers.get('Idempotency-Key','')
    if not 8<=len(key)<=80:raise RuleError('مفتاح العملية مطلوب')
    result=perform(request.user,m.property_id,name,data,key)
    return JsonResponse({'ok':True,**result})

@require_GET
@api_errors
def reports(request):
    m=membership(request)
    start=day(request.GET.get('start',timezone.localdate()));end=day(request.GET.get('end',start+timedelta(days=1)))
    return JsonResponse(report(m.property,start,end))

@require_GET
def health(request):
    from django.db import connection
    with connection.cursor() as cursor:cursor.execute('SELECT 1')
    return JsonResponse({'status':'ok'})

@require_GET
@api_errors
def export_view(request,dataset,fmt):
    from .exports import build_export
    m=membership(request)
    return build_export(request,m.property,dataset,fmt,m.role)

@require_GET
@api_errors
def document(request,kind,pk):
    from .exports import document_data
    p=membership(request).property
    if kind=='contract':
        contract=Contract.objects.filter(pk=pk,reservation__property=p).first()
        if not contract:raise RuleError('العقد غير موجود في منشأتك')
        from .exports import cash
        s=contract.snapshot
        context={'contract':contract,'s':s,'official':s['property'],'guest':s['guest'],'reference':f'CTR-{p.pk}-{contract.pk:06}','units':s['units'],'totals':[(label,cash(s.get(key,0))) for key,label in [('rent','الإيجار'),('discount','الخصم'),('extras','الإضافات'),('penalties','الغرامات'),('net','المجموع الجزئي'),('tax','ضريبة القيمة المضافة'),('total','المجموع الكلي')]]}
        return render(request,'contract.html',context)
    title,lines=document_data(p,kind,pk)
    return render(request,'document.html',{'title':title,'lines':lines,'kind':kind,'pk':pk})


@require_GET
@api_errors
def birth_date(request):
    from .validation import birth_dates
    membership(request)
    gregorian,hijri=birth_dates(request.GET.get('date',''))
    return JsonResponse({'birth_date':gregorian,'birth_hijri':hijri})

@require_GET
@api_errors
def photo(request,pk):
    guest=Guest.objects.filter(pk=pk,property=membership(request).property).first()
    if not guest or not guest.photo:return HttpResponse(status=404)
    response=HttpResponse(bytes(guest.photo),content_type='image/jpeg')
    response['Cache-Control']='private, no-store'
    return response


@require_GET
def shared_contract(request,token):
    from django.core import signing
    from django.shortcuts import get_object_or_404
    try:data=signing.loads(token,salt='hoteza-contract-share',max_age=72*3600)
    except signing.BadSignature:return HttpResponse('رابط العقد غير صالح أو منتهي الصلاحية',status=404)
    contract=get_object_or_404(Contract,pk=data.get('contract'));s=contract.snapshot
    from .exports import cash
    response=render(request,'contract.html',{'contract':contract,'s':s,'official':s['property'],'guest':s['guest'],'reference':f'CTR-{contract.reservation.property_id}-{contract.pk:06}','units':s['units'],'shared':True,'totals':[(label,cash(s.get(key,0))) for key,label in [('rent','الإيجار'),('discount','الخصم'),('extras','الإضافات'),('penalties','الغرامات'),('net','المجموع الجزئي'),('tax','ضريبة القيمة المضافة'),('total','المجموع الكلي')]]})
    response['Cache-Control']='private, no-store';response['Referrer-Policy']='no-referrer';response['X-Robots-Tag']='noindex, nofollow'
    return response
