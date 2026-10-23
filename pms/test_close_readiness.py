from datetime import timedelta,datetime,time
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Property,Membership,Guest,Reservation,Payment,Charge,JournalEntry,LedgerReconciliation,Audit,Operation
from .ledger import init_chart,post
from .reconciliation import opening,comparison,confirm
from .ledger_sources import preview,apply
from .close_readiness import review
from .periods import lock
from .services import RuleError

class CloseReadinessTests(TestCase):
    def setUp(self):
        self.u=get_user_model().objects.create_user('readiness-owner');self.staff=get_user_model().objects.create_user('readiness-reception')
        self.p=Property.objects.create(name='جاهزية اختبار');self.q=Property.objects.create(name='عقار آخر')
        Membership.objects.create(property=self.p,user=self.u,role='owner');Membership.objects.create(property=self.p,user=self.staff,role='reception')
        init_chart(self.u,self.p.pk);self.day=timezone.localdate()-timedelta(days=1);self.end=self.day+timedelta(days=1)
        self.g=Guest.objects.create(property=self.p,name='ضيف اختبار')
        self.r=Reservation.objects.create(property=self.p,guest=self.g,arrival=self.day,departure=self.end,rate=100)
    def start(self):opening(self.u,self.p.pk,{'date':str(self.day),'reference':'OPEN-READINESS','confirm_zero':True,'lines':[]})
    def run_review(self):return review(self.u,self.p.pk,self.day,self.end)
    def reconcile(self,code,actual=0):
        p=comparison(self.u,self.p.pk,code,self.day,actual)
        return confirm(self.u,self.p.pk,{'account':code,'date':str(self.day),'actual':actual,'digest':p['digest'],'reference':'RECON-'+code+'-'+str(LedgerReconciliation.objects.count()),'explanation':'فحص الفرق المسجل'})
    def all_reconciled(self):
        for code in ['1000','1010','1020']:self.reconcile(code)
    def receipt(self):
        p=Payment.objects.create(reservation=self.r,amount=100,method='نقد',user=self.u)
        Payment.objects.filter(pk=p.pk).update(created_at=timezone.make_aware(datetime.combine(self.day,time(12))))
        return p
    def test_missing_opening_and_read_only(self):
        before=(JournalEntry.objects.count(),LedgerReconciliation.objects.count(),Audit.objects.count(),Operation.objects.count())
        result=self.run_review();self.assertIn('opening_missing',[x['code'] for x in result['blockers']]);self.assertFalse(result['certified_close'])
        self.assertEqual(before,(JournalEntry.objects.count(),LedgerReconciliation.objects.count(),Audit.objects.count(),Operation.objects.count()))
    def test_only_all_three_end_day_reconciliations_pass(self):
        self.start();self.reconcile('1000');self.assertFalse(self.run_review()['checks_passed'])
        self.reconcile('1010');self.reconcile('1020');r=self.run_review()
        self.assertTrue(r['checks_passed']);self.assertFalse(r['certified_close']);self.assertEqual(r['source_count'],0)
        self.assertEqual(r['digest'],self.run_review()['digest'])
    def test_difference_and_stale_are_visible(self):
        self.start();self.all_reconciled();self.reconcile('1000',100)
        r=self.run_review();self.assertEqual(r['reconciliations'][0]['status'],'difference')
        post(self.u,self.p.pk,source='new-manual',entry_date=self.day,description='تعديل رصيد بعد المطابقة',lines=[{'account':'1000','debit':100},{'account':'3000','credit':100}])
        r=self.run_review();self.assertEqual(r['reconciliations'][0]['status'],'stale');self.assertFalse(r['checks_passed'])
    def test_pending_receipt_disappears_after_explicit_posting(self):
        self.start();p=self.receipt();before=JournalEntry.objects.count();r=self.run_review()
        row=next(x for x in r['sources'] if x['kind']=='payment');self.assertEqual(row['new'],1);self.assertEqual(JournalEntry.objects.count(),before)
        plan=preview(self.u,self.p.pk,'payment',p.pk);apply(self.u,self.p.pk,'payment',p.pk,plan['digest'])
        r=self.run_review();row=next(x for x in r['sources'] if x['kind']=='payment');self.assertEqual(row['status'],'reviewed')
    def test_locked_period_still_reveals_unposted_sources(self):
        self.start();lock(self.u,self.p.pk,{'date':str(self.day),'kind':'daily','reason':'قفل تجريبي قبل ظهور مصدر','acknowledge_scope':True})
        self.receipt();r=self.run_review();row=next(x for x in r['sources'] if x['kind']=='payment')
        self.assertEqual(row['new'],1);self.assertEqual(row['status'],'pending');self.assertEqual(JournalEntry.objects.count(),0)
    def test_changed_posted_receipt_is_conflict(self):
        self.start();p=self.receipt();plan=preview(self.u,self.p.pk,'payment',p.pk);apply(self.u,self.p.pk,'payment',p.pk,plan['digest'])
        Payment.objects.filter(pk=p.pk).update(amount=200)
        row=next(x for x in self.run_review()['sources'] if x['kind']=='payment');self.assertEqual(row['conflicts'],1)
    def test_open_stay_accrual_is_blocked_not_ignored(self):
        self.start();Charge.objects.create(reservation=self.r,service_date=self.day,description='ليلة مقيم',net=100)
        row=next(x for x in self.run_review()['sources'] if x['kind']=='reservation');self.assertEqual(row['status'],'blocked');self.assertFalse(self.run_review()['checks_passed'])
    def test_scan_limit_cannot_return_green(self):
        self.start();self.all_reconciled();self.receipt()
        with patch('pms.close_readiness.LIMIT',1):
            r=self.run_review();self.assertEqual(r['source_count'],2);self.assertEqual(r['scanned'],1);self.assertFalse(r['complete_scan']);self.assertFalse(r['checks_passed'])
    def test_future_current_and_bad_range(self):
        self.start();self.all_reconciled()
        r=review(self.u,self.p.pk,self.day,self.end+timedelta(days=1));self.assertIn('period_incomplete',[x['code'] for x in r['blockers']])
        for start,end in [(self.end,self.day),(self.day,self.end+timedelta(days=2)),(self.day-timedelta(days=400),self.end)]:
            with self.assertRaises(RuleError):review(self.u,self.p.pk,start,end)
    def test_owner_tenant_and_api_boundary(self):
        self.start()
        with self.assertRaises(RuleError):review(self.staff,self.p.pk,self.day,self.end)
        with self.assertRaises(RuleError):review(self.u,self.q.pk,self.day,self.end)
        self.client.force_login(self.u);session=self.client.session;session['property_id']=self.p.pk;session.save()
        response=self.client.get('/api/ledger/close-readiness/',{'start':str(self.day),'end':str(self.end),'property':self.q.pk})
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['property'],self.p.pk);self.assertEqual(response['Cache-Control'],'private, no-store')
        self.client.force_login(self.staff);self.assertEqual(self.client.get('/api/ledger/close-readiness/').status_code,400)
