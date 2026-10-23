from datetime import timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import Property,Membership,JournalEntry,JournalLine,LedgerAccount,Audit
from .ledger import init_chart,post,reverse,trial_balance
from .services import RuleError,perform
import uuid,json

class LedgerTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_user('ledger-owner');self.staff=get_user_model().objects.create_user('ledger-staff');self.outsider=get_user_model().objects.create_user('outsider')
        self.p=Property.objects.create(name='عقار أ');self.q=Property.objects.create(name='عقار ب')
        Membership.objects.create(property=self.p,user=self.owner,role='owner');Membership.objects.create(property=self.p,user=self.staff,role='reception');Membership.objects.create(property=self.q,user=self.outsider,role='owner')
        self.today=timezone.localdate();init_chart(self.owner,self.p.pk)
        self.lines=[{'account':'1000','debit':10000},{'account':'3000','credit':10000}]
    def entry(self,**kw):
        data=dict(source='opening:test',entry_date=self.today,description='افتتاحي اختبار',lines=self.lines);data.update(kw)
        return post(self.owner,self.p.pk,**data)
    def test_balanced_post_and_source_idempotency(self):
        e=self.entry();self.assertEqual(e.debit_total,10000);self.assertEqual(e.lines.count(),2)
        self.assertEqual(e.pk,self.entry().pk);self.assertEqual(JournalEntry.objects.count(),1)
        with self.assertRaises(RuleError):self.entry(description='مرجع مكرر مختلف')
    def test_reject_unbalanced_and_invalid_values_atomically(self):
        for lines in [[{'account':'1000','debit':1},{'account':'3000','credit':2}],[{'account':'1000','debit':True},{'account':'3000','credit':1}],[{'account':'1000','debit':1.5},{'account':'3000','credit':1.5}],[{'account':'1000','debit':10,'credit':10},{'account':'3000','credit':1}],[{'account':'missing','debit':1},{'account':'3000','credit':1}]]:
            with self.subTest(lines=lines),self.assertRaises(RuleError):self.entry(lines=lines)
        self.assertEqual(JournalEntry.objects.count(),0);self.assertEqual(JournalLine.objects.count(),0)
    def test_owner_permission_and_tenant_isolation(self):
        for user in [self.staff,self.outsider]:
            with self.assertRaises(RuleError):init_chart(user,self.p.pk)
            with self.assertRaises(RuleError):trial_balance(user,self.p.pk,self.today,self.today+timedelta(days=1))
        with self.assertRaises(RuleError):post(self.owner,self.q.pk,source='x',entry_date=self.today,description='خارج العقار',lines=self.lines)
    def test_foreign_reservation_rejected(self):
        from .models import Guest,Reservation
        g=Guest.objects.create(property=self.q,name='ضيف آخر');r=Reservation.objects.create(property=self.q,guest=g,arrival=self.today,departure=self.today+timedelta(days=1),rate=100)
        with self.assertRaises(RuleError):self.entry(lines=[{'account':'1000','debit':1,'reservation':r.pk},{'account':'3000','credit':1}])
    def test_immutable_and_reversal(self):
        e=self.entry()
        for action in [lambda:e.save(),lambda:e.delete(),lambda:JournalEntry.objects.filter(pk=e.pk).update(description='تعديل'),lambda:JournalEntry.objects.filter(pk=e.pk).delete(),lambda:e.lines.update(debit=20),lambda:e.lines.first().save()]:
            with self.assertRaises(ValidationError):action()
        rev=reverse(self.owner,self.p.pk,e.pk,self.today,'عكس افتتاحي اختبار');self.assertEqual(rev.sequence,2)
        self.assertEqual(rev.pk,reverse(self.owner,self.p.pk,e.pk,self.today,'عكس افتتاحي اختبار').pk)
        rep=trial_balance(self.owner,self.p.pk,self.today,self.today+timedelta(days=1));self.assertEqual(rep['closing_debit'],0);self.assertEqual(rep['closing_credit'],0)
        with self.assertRaises(RuleError):reverse(self.owner,self.p.pk,rev.pk,self.today,'لا تعكس العكس')
    def test_period_opening_and_no_future_posting(self):
        self.entry(entry_date=self.today-timedelta(days=2));rep=trial_balance(self.owner,self.p.pk,self.today,self.today+timedelta(days=1))
        cash=next(x for x in rep['rows'] if x['code']=='1000');self.assertEqual(cash['opening'],10000);self.assertEqual(cash['debit'],0);self.assertEqual(rep['closing_debit'],rep['closing_credit'])
        with self.assertRaises(RuleError):self.entry(source='future',entry_date=self.today+timedelta(days=1))
    def test_api_audit_and_reception_denied(self):
        self.client.force_login(self.owner);key=str(uuid.uuid4());data={'date':str(self.today),'description':'افتتاحي من API','lines':self.lines}
        response=self.client.post('/api/action/journal_post/',data=json.dumps(data),content_type='application/json',HTTP_IDEMPOTENCY_KEY=key);self.assertEqual(response.status_code,200)
        self.assertTrue(Audit.objects.filter(property=self.p,action='journal_post').exists())
        read=self.client.get('/api/ledger/');self.assertEqual(read.status_code,200);self.assertEqual(read.json()['entries'][0]['id'],response.json()['journal'])
        self.client.force_login(self.staff);self.assertEqual(self.client.get('/api/ledger/').status_code,400)
        denied=self.client.post('/api/action/journal_post/',data=json.dumps(data),content_type='application/json',HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()));self.assertEqual(denied.status_code,400)
        self.client.force_login(self.outsider);other=self.client.get('/api/ledger/');self.assertEqual(other.json()['entries'],[])
    def test_init_chart_repeat_does_not_create_balance(self):
        self.assertEqual(init_chart(self.owner,self.p.pk),11);self.assertEqual(JournalEntry.objects.count(),0)
        rep=trial_balance(self.owner,self.p.pk,self.today,self.today+timedelta(days=1));self.assertEqual(rep['debit'],0);self.assertIn('لم ترحل',rep['notice'])
    def test_currency_change_never_mixes_money(self):
        self.entry();self.p.currency='USD';self.p.save()
        with self.assertRaises(RuleError):self.entry(source='different-currency')
        with self.assertRaises(RuleError):trial_balance(self.owner,self.p.pk,self.today,self.today+timedelta(days=1))
