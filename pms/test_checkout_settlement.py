import uuid
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Property,Membership,Unit,Guest,Reservation,Allocation,Charge,Payment,Invoice,Audit
from .services import perform,RuleError,balance
from .checkout import preview

class CheckoutSettlementTests(TestCase):
    def setUp(self):
        self.u=get_user_model().objects.create_user('settlement-owner');self.staff=get_user_model().objects.create_user('settlement-staff')
        self.p=Property.objects.create(name='عقار اختبار',tax_rate=15);Membership.objects.create(property=self.p,user=self.u,role='owner');Membership.objects.create(property=self.p,user=self.staff,role='reception')
        self.today=timezone.localdate();self.unit=Unit.objects.create(property=self.p,number='101',kind='استوديو')
        g=Guest.objects.create(property=self.p,name='ضيف تجريبي');self.r=Reservation.objects.create(property=self.p,guest=g,arrival=self.today-timedelta(days=1),departure=self.today,rate=10000,status='checked_in')
        Allocation.objects.create(reservation=self.r,unit=self.unit,start=self.r.arrival,end=self.r.departure,rate=10000)
        Charge.objects.create(reservation=self.r,service_date=self.r.arrival,description='إقامة ليلة',net=10000,tax=1500,kind='room')
    def data(self,**kw):return {'id':self.r.pk,'settlement_ack':True,'settlement_digest':preview(self.u,self.p.pk,self.r.pk)['digest'],'settlement_mode':'collect','method':'نقد',**kw}
    def checkout(self,d,user=None,key=None):return perform(user or self.u,self.p.pk,'checkout',d,key or str(uuid.uuid4()))
    def test_one_save_collects_invoices_and_checks_out_idempotently(self):
        d=self.data();key=str(uuid.uuid4());result=self.checkout(d,key=key);self.assertEqual(result,self.checkout(d,key=key))
        self.r.refresh_from_db();self.unit.refresh_from_db();self.assertEqual(self.r.status,'checked_out');self.assertEqual(self.unit.cleaning,'dirty');self.assertEqual(balance(self.r)['balance'],0)
        self.assertEqual(Payment.objects.count(),1);self.assertEqual(Payment.objects.get().amount,11500);self.assertEqual(Invoice.objects.get().total,11500)
        record=Audit.objects.get(pk=result['settlement']);self.assertEqual(record.details['before']['balance'],11500);self.assertEqual(record.details['after']['balance'],0)
    def test_review_and_ack_cannot_be_bypassed(self):
        for d in [{'id':self.r.pk},self.data(settlement_ack=False),self.data(settlement_digest='old')]:
            with self.assertRaises(RuleError):self.checkout(d)
        self.assertEqual(Payment.objects.count(),0);self.assertEqual(Invoice.objects.count(),0)
    def test_stale_account_and_invalid_method_leave_everything_unchanged(self):
        d=self.data();Charge.objects.create(reservation=self.r,service_date=self.today,description='خدمة جديدة',net=100)
        with self.assertRaises(RuleError):self.checkout(d)
        with self.assertRaises(RuleError):self.checkout(self.data(method='غير مدعوم'))
        self.r.refresh_from_db();self.assertEqual(self.r.status,'checked_in');self.assertEqual(Payment.objects.count(),0)
    def test_refund_is_exact_and_owner_only(self):
        Payment.objects.create(reservation=self.r,amount=15000,method='نقد',user=self.u)
        d=self.data(settlement_mode='refund')
        with self.assertRaises(RuleError):self.checkout(d,user=self.staff)
        result=self.checkout(d);self.assertEqual(Payment.objects.get(pk=result['voucher']).amount,-3500);self.assertEqual(balance(self.r)['balance'],0)
    def test_zero_balance_still_records_settlement(self):
        Payment.objects.create(reservation=self.r,amount=11500,method='نقد',user=self.u)
        result=self.checkout(self.data(settlement_mode='none'));self.assertIsNone(result['voucher']);self.assertEqual(Payment.objects.count(),1);self.assertTrue(result['settlement'])
    def test_debt_needs_owner_and_documented_reason(self):
        with self.assertRaises(RuleError):self.checkout(self.data(settlement_mode='debt',debt_reason=''))
        with self.assertRaises(RuleError):self.checkout(self.data(settlement_mode='debt',debt_reason='مديونية موثقة للاختبار'),user=self.staff)
        self.checkout(self.data(settlement_mode='debt',debt_reason='مديونية موثقة للاختبار'));self.assertEqual(balance(self.r)['balance'],11500);self.assertEqual(Payment.objects.count(),0)
    def test_invoice_failure_rolls_back_the_voucher_and_checkout(self):
        # A negative uninvoiced correction cannot be silently put on a new invoice.
        Charge.objects.create(reservation=self.r,service_date=self.today,description='تصحيح غير مفوتر',net=-100,kind='adjustment')
        with self.assertRaises(RuleError):self.checkout(self.data())
        self.r.refresh_from_db();self.assertEqual(self.r.status,'checked_in');self.assertEqual(Payment.objects.count(),0);self.assertEqual(Audit.objects.count(),0)
    def test_overdue_requires_extension_and_early_requires_night_settlement(self):
        self.r.departure=self.today-timedelta(days=1);self.r.arrival=self.today-timedelta(days=2);self.r.save()
        self.assertTrue(preview(self.u,self.p.pk,self.r.pk)['blockers'])
        with self.assertRaises(RuleError):self.checkout(self.data())
        self.r.departure=self.today+timedelta(days=2);self.r.save()
        with self.assertRaises(RuleError):self.checkout(self.data())
    def test_preview_is_read_only_and_tenant_scoped(self):
        q=Property.objects.create(name='آخر')
        with self.assertRaises(RuleError):preview(self.u,q.pk,self.r.pk)
        self.client.force_login(self.u);session=self.client.session;session['property_id']=self.p.pk;session.save()
        response=self.client.get('/api/checkout/preview/',{'id':self.r.pk});self.assertEqual(response.status_code,200);self.assertEqual(response['Cache-Control'],'private, no-store');self.assertEqual(Payment.objects.count(),0)
