from datetime import timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import Property,Membership,LedgerPeriodLock,LedgerPeriodReopen,JournalEntry
from .ledger import init_chart,post,reverse
from .reconciliation import opening
from .periods import lock,reopen,state
from .services import RuleError,perform

class PeriodTests(TestCase):
    def setUp(self):
        self.u=get_user_model().objects.create_user('period-owner')
        self.staff=get_user_model().objects.create_user('period-staff')
        self.p=Property.objects.create(name='قفل اختبار')
        Membership.objects.create(property=self.p,user=self.u,role='owner')
        Membership.objects.create(property=self.p,user=self.staff,role='reception')
        self.day=timezone.localdate()-timedelta(days=2)
        init_chart(self.u,self.p.pk)
        opening(self.u,self.p.pk,{'date':str(self.day-timedelta(days=40)),'reference':'OPEN-PERIOD','confirm_zero':True,'lines':[]})
    def data(self,**kw):return {'date':str(self.day),'kind':'daily','reason':'مراجعة دفتر الفترة التجريبية','acknowledge_scope':True,**kw}
    def entry(self,dt=None,source='sample'):
        return post(self.u,self.p.pk,source=source,entry_date=dt or self.day,description='قيد اختبار قفل الفترة',lines=[{'account':'1000','debit':100},{'account':'3000','credit':100}])
    def test_lock_blocks_new_entry_but_exact_retry_survives(self):
        e=self.entry();item=lock(self.u,self.p.pk,self.data())
        self.assertEqual(self.entry().pk,e.pk)
        with self.assertRaises(RuleError):self.entry(source='new')
        self.entry(self.day+timedelta(days=1),'next')
        self.assertEqual(LedgerPeriodLock.objects.get(pk=item['lock']).snapshot['debit'],100)
    def test_reverse_requires_open_date(self):
        e=self.entry();lock(self.u,self.p.pk,self.data())
        with self.assertRaises(RuleError):reverse(self.u,self.p.pk,e.pk,self.day,'تصحيح داخل فترة مقفلة')
        reverse(self.u,self.p.pk,e.pk,self.day+timedelta(days=1),'تصحيح في فترة مفتوحة')
    def test_reopening_is_immutable_and_audited(self):
        result=perform(self.u,self.p.pk,'ledger_period_lock',self.data(),'lock-key')
        with self.assertRaises(RuleError):reopen(self.u,self.p.pk,{'id':result['lock'],'reason':'قصير'})
        perform(self.u,self.p.pk,'ledger_period_reopen',{'id':result['lock'],'reason':'إعادة فتح لتصحيح خطأ موثق'},'reopen-key')
        self.entry();self.assertFalse(state(self.u,self.p.pk)[0]['active'])
        with self.assertRaises(ValidationError):LedgerPeriodReopen.objects.first().delete()
        with self.assertRaises(ValidationError):LedgerPeriodLock.objects.first().delete()
    def test_invalid_scope_future_overlap_and_permission(self):
        for d in [self.data(acknowledge_scope=False),self.data(date=str(timezone.localdate())),self.data(kind='other'),self.data(kind='monthly',date=str(self.day.replace(day=2)))]:
            with self.assertRaises(RuleError):lock(self.u,self.p.pk,d)
        with self.assertRaises(RuleError):lock(self.staff,self.p.pk,self.data())
        lock(self.u,self.p.pk,self.data())
        with self.assertRaises(RuleError):lock(self.u,self.p.pk,self.data())
    def test_month_boundaries_and_tenant_isolation(self):
        month=(self.day.replace(day=1)-timedelta(days=1)).replace(day=1)
        # Opening may be later than this calendar month: move test cutover earlier by rebuilding property.
        q=Property.objects.create(name='عقار منفصل');Membership.objects.create(property=q,user=self.u,role='owner')
        init_chart(self.u,q.pk);opening(self.u,q.pk,{'date':str(month),'reference':'OPEN-MONTH','confirm_zero':True,'lines':[]})
        item=lock(self.u,q.pk,self.data(kind='monthly',date=str(month)))
        self.assertEqual(state(self.u,self.p.pk),[])
        with self.assertRaises(RuleError):reopen(self.u,self.p.pk,{'id':item['lock'],'reason':'لا يسمح بعقار آخر هنا'})
        self.entry()
