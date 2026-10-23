from datetime import timedelta
import uuid,json
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import Property,Membership,JournalEntry,LedgerOpening,LedgerReconciliation,Payment,Reservation,Guest
from .ledger import init_chart,post,reverse,trial_balance
from .reconciliation import opening,comparison,confirm,transfer,state
from .ledger_sources import preview
from .services import perform,RuleError

class ReconciliationTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_user('balance-owner');self.staff=get_user_model().objects.create_user('balance-staff')
        self.p=Property.objects.create(name='عقار أ');self.q=Property.objects.create(name='عقار ب')
        Membership.objects.create(property=self.p,user=self.owner,role='owner');Membership.objects.create(property=self.p,user=self.staff,role='reception')
        init_chart(self.owner,self.p.pk);self.today=timezone.localdate()
    def start(self,lines=None,**kw):
        d={'date':str(self.today),'reference':'OPEN-TEST','lines':lines or [],'confirm_zero':not lines,**kw}
        return opening(self.owner,self.p.pk,d)
    def cash(self):return self.start([{'account':'1000','debit':10000},{'account':'3000','credit':10000}])
    def change(self,amount=100):
        return post(self.owner,self.p.pk,source=str(uuid.uuid4()),entry_date=self.today,description='حركة اختبار بعد الافتتاح',lines=[{'account':'1000','debit':amount},{'account':'3000','credit':amount}])
    def plan(self,actual=10000,account='1000'):return comparison(self.owner,self.p.pk,account,self.today,actual)
    def record(self,p,reference='RECON-TEST',explanation=''):
        return confirm(self.owner,self.p.pk,{'account':p['account'],'date':p['date'],'actual':p['actual'],'digest':p['digest'],'reference':reference,'explanation':explanation})
    def test_balanced_opening_is_previous_day_and_unique(self):
        result=self.cash();e=JournalEntry.objects.get(pk=result['journal']);self.assertEqual(e.date,self.today-timedelta(days=1))
        r=trial_balance(self.owner,self.p.pk,self.today,self.today+timedelta(days=1));cash=next(x for x in r['rows'] if x['code']=='1000')
        self.assertEqual(cash['opening'],10000);self.assertEqual(cash['debit'],0)
        with self.assertRaises(RuleError):self.cash()
        with self.assertRaises(RuleError):reverse(self.owner,self.p.pk,e.pk,self.today,'عكس غير مسموح للافتتاح')
        with self.assertRaises(ValidationError):LedgerOpening.objects.get(property=self.p).delete()
        self.assertEqual(JournalEntry.objects.count(),1)
    def test_zero_opening_requires_explicit_acknowledgment(self):
        with self.assertRaises(RuleError):self.start(confirm_zero=False)
        self.assertEqual(LedgerOpening.objects.count(),0)
        result=self.start();self.assertIsNone(result['journal']);self.assertEqual(JournalEntry.objects.count(),0)
    def test_invalid_opening_rolls_back_and_only_balance_sheet(self):
        for lines in [[{'account':'1000','debit':100},{'account':'3000','credit':90}],[{'account':'1000','debit':100},{'account':'4000','credit':100}]]:
            with self.assertRaises(RuleError):self.start(lines)
        self.assertEqual(JournalEntry.objects.count(),0);self.assertEqual(LedgerOpening.objects.count(),0)
    def test_opening_after_existing_journal_is_rejected(self):
        self.change()
        with self.assertRaises(RuleError):self.cash()
        self.assertEqual(LedgerOpening.objects.count(),0)
    def test_unallocated_customer_balance_needs_acknowledgment(self):
        lines=[{'account':'1000','debit':100},{'account':'2000','credit':100}]
        with self.assertRaises(RuleError):self.start(lines)
        self.start(lines,allow_unallocated=True);self.assertTrue(LedgerOpening.objects.get(property=self.p).unallocated_ack)
    def test_cutoff_rejects_old_journal_and_old_receipt(self):
        self.start()
        with self.assertRaises(RuleError):post(self.owner,self.p.pk,source='old',entry_date=self.today-timedelta(days=1),description='تكرار تاريخ قديم',lines=[{'account':'1000','debit':1},{'account':'3000','credit':1}])
        g=Guest.objects.create(property=self.p,name='ضيف');r=Reservation.objects.create(property=self.p,guest=g,arrival=self.today,departure=self.today+timedelta(days=1),rate=100)
        p=Payment.objects.create(reservation=r,amount=100,method='نقد',user=self.owner)
        Payment.objects.filter(pk=p.pk).update(created_at=timezone.now()-timedelta(days=1))
        with self.assertRaises(RuleError):preview(self.owner,self.p.pk,'payment',p.pk)
        self.assertEqual(JournalEntry.objects.count(),0)
    def test_matching_record_has_no_financial_side_effect(self):
        self.cash();plan=self.plan();self.assertEqual(plan['difference'],0);self.assertEqual(LedgerReconciliation.objects.count(),0)
        self.record(plan);self.assertEqual(JournalEntry.objects.count(),1)
        row=state(self.owner,self.p.pk,self.today,self.today+timedelta(days=1))['reconciliations'][0];self.assertFalse(row['stale'])
        with self.assertRaises(ValidationError):LedgerReconciliation.objects.first().save()
    def test_difference_requires_explanation_and_never_balances_itself(self):
        self.cash();p=self.plan(9000);self.assertEqual(p['difference'],-1000)
        with self.assertRaises(RuleError):self.record(p)
        result=self.record(p,explanation='عجز قيد المراجعة');self.assertEqual(result['difference'],-1000);self.assertEqual(JournalEntry.objects.count(),1)
    def test_stale_comparison_rejected_and_saved_record_becomes_stale(self):
        self.cash();p=self.plan();self.change()
        with self.assertRaises(RuleError):self.record(p)
        self.assertEqual(LedgerReconciliation.objects.count(),0)
        self.record(self.plan(10100));self.change()
        row=state(self.owner,self.p.pk,self.today,self.today+timedelta(days=1))['reconciliations'][0];self.assertTrue(row['stale'])
    def test_duplicate_reference_and_isolation(self):
        self.cash();self.record(self.plan())
        with self.assertRaises(RuleError):self.record(self.plan())
        with self.assertRaises(RuleError):comparison(self.staff,self.p.pk,'1000',self.today,10000)
        with self.assertRaises(RuleError):comparison(self.owner,self.q.pk,'1000',self.today,10000)
        self.assertEqual(LedgerReconciliation.objects.count(),1)
    def test_reconciliation_before_opening_and_invalid_account_date_rejected(self):
        with self.assertRaises(RuleError):self.plan()
        self.cash()
        for account,dt,actual in [('4000',self.today,100),('1000',self.today-timedelta(days=1),100),('1000',self.today+timedelta(days=1),100),('1000',self.today,True)]:
            with self.assertRaises(RuleError):comparison(self.owner,self.p.pk,account,dt,actual)
    def test_transfer_with_fees_and_no_income_duplication(self):
        self.cash();d={'from_account':'1000','to_account':'1010','amount':5000,'fee':100,'date':str(self.today),'reference':'BANK-TRANSFER-1'}
        result=transfer(self.owner,self.p.pk,d);self.assertEqual(transfer(self.owner,self.p.pk,d),result)
        self.assertEqual(self.plan(0)['book'],5000);self.assertEqual(self.plan(0,'1010')['book'],4900)
        report=trial_balance(self.owner,self.p.pk,self.today,self.today+timedelta(days=1));rows={x['code']:x for x in report['rows']}
        self.assertEqual(rows['5000']['debit'],100);self.assertEqual(rows['4000']['credit'],0)
        with self.assertRaises(RuleError):transfer(self.owner,self.p.pk,{**d,'fee':200})
        reverse(self.owner,self.p.pk,result['journal'],self.today,'عكس تحويل اختبار')
        with self.assertRaises(RuleError):transfer(self.owner,self.p.pk,d)
    def test_transfer_insufficient_funds_and_same_account_rejected(self):
        self.cash();d={'from_account':'1000','to_account':'1010','amount':10001,'fee':0,'date':str(self.today),'reference':'BANK-TRANSFER-2'}
        with self.assertRaises(RuleError):transfer(self.owner,self.p.pk,d)
        with self.assertRaises(RuleError):transfer(self.owner,self.p.pk,{**d,'to_account':'1000','amount':10})
        self.assertEqual(JournalEntry.objects.count(),1)
    def test_api_opening_and_reconciliation_are_idempotent_audited_and_owner_only(self):
        self.client.force_login(self.owner)
        d={'date':str(self.today),'reference':'API-OPEN','lines':[],'confirm_zero':True};key=str(uuid.uuid4())
        def call(action,data,key):return self.client.post('/api/action/'+action+'/',data=json.dumps(data),content_type='application/json',HTTP_IDEMPOTENCY_KEY=key)
        one=call('journal_opening',d,key);self.assertEqual(one.status_code,200);self.assertEqual(one.json(),call('journal_opening',d,key).json())
        p=self.client.get('/api/ledger/reconciliation-preview/?account=1000&date='+str(self.today)+'&actual=0').json()
        rec={'account':'1000','date':str(self.today),'actual':0,'reference':'API-RECON','digest':p['digest']};key2=str(uuid.uuid4())
        one=call('reconciliation_create',rec,key2);self.assertEqual(one.status_code,200);self.assertEqual(one.json(),call('reconciliation_create',rec,key2).json())
        from .models import Audit
        self.assertTrue(Audit.objects.filter(property=self.p,action='reconciliation_create').exists())
        self.client.force_login(self.staff);self.assertEqual(call('journal_opening',d,str(uuid.uuid4())).status_code,400)
        self.assertEqual(self.client.get('/api/ledger/reconciliation-preview/?account=1000&date='+str(self.today)+'&actual=0').status_code,400)

    def test_negative_physical_cash_rejected_but_bank_overdraft_visible(self):
        with self.assertRaises(RuleError):self.start([{'account':'1000','credit':100},{'account':'3000','debit':100}])
        self.start()
        with self.assertRaises(RuleError):self.plan(-100)
        self.assertEqual(self.plan(-100,'1010')['difference'],-100)
