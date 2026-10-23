from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Property,Membership,Unit,Guest,Reservation,Payment,Expense,JournalEntry,JournalLine
from .ledger import init_chart,trial_balance
from .ledger_sources import preview,apply
from .services import perform,RuleError,balance
import uuid

class PostingSourceTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_user('posting-owner');self.staff=get_user_model().objects.create_user('posting-staff')
        self.p=Property.objects.create(name='عقار ترحيل',tax_rate=15);self.q=Property.objects.create(name='عقار آخر')
        Membership.objects.create(property=self.p,user=self.owner,role='owner');Membership.objects.create(property=self.p,user=self.staff,role='reception')
        self.u=Unit.objects.create(property=self.p,number='1',kind='استوديو')
        self.g=Guest.objects.create(property=self.p,name='ضيف اختبار',phone='0500000000',email='test@example.com',region='عسير',city='أبها',street='عنوان الاختبار')
        self.today=timezone.localdate();self.start=self.today-timedelta(days=2)
        init_chart(self.owner,self.p.pk)
        with patch('pms.services.timezone.localdate',return_value=self.start):
            rid=self.op('reservation_create',{'guest':self.g.pk,'unit':self.u.pk,'arrival':str(self.start),'departure':str(self.today),'rate':'100','persons':1})['id'];self.r=Reservation.objects.get(pk=rid);self.op('checkin',{'id':rid})
        self.r.refresh_from_db()
    def op(self,action,data):return perform(self.owner,self.p.pk,action,data,str(uuid.uuid4()))
    def payment(self,amount,method='نقد',when=None):
        result=self.op('payment',{'id':self.r.pk,'amount':str(amount),'method':method});p=Payment.objects.get(pk=result['payment'])
        if when:Payment.objects.filter(pk=p.pk).update(created_at=timezone.now()-timedelta(days=when));p.refresh_from_db()
        return p
    def close(self,debt=False):
        from .checkout import preview as checkout_preview
        plan=checkout_preview(self.owner,self.p.pk,self.r.pk)
        self.op('checkout',{'id':self.r.pk,'settlement_ack':True,'settlement_digest':plan['digest'],'settlement_mode':'debt' if debt else 'none','debt_reason':'اعتماد مديونية لاختبار الترحيل'});self.r.refresh_from_db()
    def post(self,kind,pk):
        plan=preview(self.owner,self.p.pk,kind,pk);return apply(self.owner,self.p.pk,kind,pk,plan['digest'])
    def balances(self):
        rep=trial_balance(self.owner,self.p.pk,self.start-timedelta(days=10),self.today+timedelta(days=1));return {r['code']:r['closing_debit']-r['closing_credit'] for r in rep['rows']}
    def test_receipt_is_advance_not_revenue_and_not_duplicated(self):
        p=self.payment(230,when=2);self.post('payment',p.pk)
        b=self.balances();self.assertEqual(b['1000'],23000);self.assertEqual(b['2000'],-23000);self.assertEqual(b['4000'],0)
        self.assertEqual(self.post('payment',p.pk)['created'],0);self.assertEqual(JournalEntry.objects.count(),1)
    def test_closed_reservation_earned_revenue_allocates_advances(self):
        self.payment(230,when=2);self.close();plan=preview(self.owner,self.p.pk,'reservation',self.r.pk)
        self.assertGreater(plan['new'],0);self.assertEqual(JournalEntry.objects.count(),0)
        self.post('reservation',self.r.pk);b=self.balances()
        self.assertEqual(b['1000'],23000);self.assertEqual(b['4000'],-20000);self.assertEqual(b['2100'],-3000);self.assertEqual(b['1100'],0);self.assertEqual(b['2000'],0)
        rep=trial_balance(self.owner,self.p.pk,self.start,self.today+timedelta(days=1));self.assertEqual(rep['debit'],rep['credit'])
        self.assertEqual(self.post('reservation',self.r.pk)['created'],0)
    def test_debt_and_late_receipt_do_not_double_count_revenue(self):
        self.payment(100,method='شبكة',when=2);self.close(debt=True);self.post('reservation',self.r.pk)
        b=self.balances();self.assertEqual(b['1100'],13000);self.assertEqual(b['1020'],10000)
        self.payment(130,method='تحويل');self.post('reservation',self.r.pk)
        b=self.balances();self.assertEqual(b['1100'],0);self.assertEqual(b['1010'],13000);self.assertEqual(b['4000'],-20000)
    def test_expense_separate_from_guest_and_date_scoped(self):
        result=self.op('expense',{'amount':'30','method':'تحويل','beneficiary':'مورد','description':'صيانة اختبار'})
        before=balance(self.r);self.post('expense',result['expense']);b=self.balances()
        self.assertEqual(b['5000'],3000);self.assertEqual(b['1010'],-3000);self.assertEqual(balance(self.r),before)
    def test_overpayment_refund_leaves_correct_liability(self):
        self.payment(300,when=2)
        self.op('refund',{'id':self.r.pk,'amount':'50','method':'نقد'})
        # Checkout protects outstanding guest credit. Review posting only after refund settles it.
        self.op('refund',{'id':self.r.pk,'amount':'20','method':'نقد'});self.close();self.post('reservation',self.r.pk)
        b=self.balances();self.assertEqual(b['1000'],23000);self.assertEqual(b['2000'],0);self.assertEqual(b['4000'],-20000)
    def test_stale_preview_and_changed_posted_source_are_rejected(self):
        p=self.payment(230,when=2);plan=preview(self.owner,self.p.pk,'payment',p.pk)
        Payment.objects.filter(pk=p.pk).update(amount=24000)
        with self.assertRaises(RuleError):apply(self.owner,self.p.pk,'payment',p.pk,plan['digest'])
        self.assertEqual(JournalEntry.objects.count(),0);self.post('payment',p.pk)
        Payment.objects.filter(pk=p.pk).update(amount=25000)
        plan=preview(self.owner,self.p.pk,'payment',p.pk);self.assertEqual(plan['conflicts'],1)
        with self.assertRaises(RuleError):apply(self.owner,self.p.pk,'payment',p.pk,plan['digest'])
        self.assertEqual(JournalEntry.objects.count(),1)
    def test_owner_and_property_guards(self):
        p=self.payment(230)
        with self.assertRaises(RuleError):preview(self.staff,self.p.pk,'payment',p.pk)
        with self.assertRaises(RuleError):preview(self.owner,self.q.pk,'payment',p.pk)
        with self.assertRaises(RuleError):preview(self.owner,self.p.pk,'reservation',self.r.pk)
        self.client.force_login(self.staff);self.assertEqual(self.client.get(f'/api/ledger/preview/?kind=payment&id={p.pk}').status_code,400)
    def test_batch_rolls_back_if_required_account_missing(self):
        self.payment(230,when=2);self.close();plan=preview(self.owner,self.p.pk,'reservation',self.r.pk)
        from .models import LedgerAccount
        LedgerAccount.objects.filter(property=self.p,code='4000').delete()
        with self.assertRaises(RuleError):apply(self.owner,self.p.pk,'reservation',self.r.pk,plan['digest'])
        self.assertEqual(JournalEntry.objects.count(),0)

    def test_import_api_is_audited_and_idempotent(self):
        import json
        from .models import Audit
        p=self.payment(230,when=2);self.client.force_login(self.owner)
        plan=self.client.get(f'/api/ledger/preview/?kind=payment&id={p.pk}').json()
        data={'kind':'payment','source_id':p.pk,'digest':plan['digest']};key=str(uuid.uuid4())
        def call():return self.client.post('/api/action/journal_import/',data=json.dumps(data),content_type='application/json',HTTP_IDEMPOTENCY_KEY=key)
        result=call();self.assertEqual(result.status_code,200);self.assertEqual(result.json()['created'],1)
        self.assertEqual(result.json(),call().json());self.assertEqual(JournalEntry.objects.count(),1)
        self.assertTrue(Audit.objects.filter(property=self.p,action='journal_import').exists())
        self.client.force_login(self.staff);self.assertEqual(call().status_code,400)
    def test_future_cancelled_nights_do_not_become_revenue(self):
        from .models import Charge,Invoice
        self.payment(230,when=2);self.close();inv=Invoice.objects.filter(reservation=self.r).first()
        later=self.today+timedelta(days=2)
        for n,kind in [(10000,'room'),(-10000,'room_reversal')]:Charge.objects.create(reservation=self.r,service_date=later,description='ليلة ملغاة تجريبية',net=n,tax=n*15//100,kind=kind,invoice=inv)
        plan=preview(self.owner,self.p.pk,'reservation',self.r.pk)
        self.assertFalse(any(x['entry_date']>str(self.today) for x in plan['entries']))
        self.post('reservation',self.r.pk);self.assertEqual(self.balances()['4000'],-20000)
