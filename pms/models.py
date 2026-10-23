from datetime import time
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q

class Property(models.Model):
    name = models.CharField(max_length=160)
    address = models.CharField(max_length=300, blank=True)
    tax_number = models.CharField(max_length=30, blank=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    official = models.JSONField(default=dict,blank=True)
    contract_terms = models.JSONField(default=list,blank=True)
    currency = models.CharField(max_length=3, default='SAR')
    subscription_until = models.DateField(null=True, blank=True)

class Membership(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=[('owner','مالك'),('reception','استقبال')])
    class Meta:
        constraints = [models.UniqueConstraint(fields=['property','user'],name='membership_unique')]

class Unit(models.Model):
    property = models.ForeignKey(Property, on_delete=models.PROTECT)
    number = models.CharField(max_length=30)
    kind = models.CharField(max_length=80)
    floor = models.CharField(max_length=40, default='الأرضي')
    capacity = models.PositiveIntegerField(default=2)
    rate = models.PositiveIntegerField(default=15000)  # integer minor currency units
    cleaning = models.CharField(max_length=20, default='ready')
    active = models.BooleanField(default=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['property','number'],name='unit_number_unique'),models.CheckConstraint(condition=Q(capacity__gt=0),name='unit_capacity_positive')]

class Guest(models.Model):
    property = models.ForeignKey(Property,on_delete=models.PROTECT)
    name = models.CharField(max_length=160)
    phone = models.CharField(max_length=40,blank=True)
    email = models.EmailField(blank=True)
    region = models.CharField(max_length=100,blank=True)
    city = models.CharField(max_length=100,blank=True)
    street = models.CharField(max_length=300,blank=True)
    profile = models.JSONField(default=dict,blank=True)
    photo = models.BinaryField(null=True,blank=True)
    show_photo = models.BooleanField(default=False)

class Reservation(models.Model):
    property = models.ForeignKey(Property,on_delete=models.PROTECT)
    guest = models.ForeignKey(Guest,on_delete=models.PROTECT)
    arrival = models.DateField()
    departure = models.DateField()
    arrival_time = models.TimeField(default=time(14,0))
    departure_time = models.TimeField(default=time(12,0))
    persons = models.PositiveIntegerField(default=1)
    rate = models.PositiveIntegerField()
    status = models.CharField(max_length=20,default='confirmed')
    rental_type = models.CharField(max_length=10,default='daily')
    visit_purpose = models.CharField(max_length=100,blank=True)
    auto_extend = models.BooleanField(default=False)
    source = models.CharField(max_length=60,default='استقبال')
    checked_in_at = models.DateTimeField(null=True,blank=True)
    checked_out_at = models.DateTimeField(null=True,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(departure__gt=models.F('arrival')),name='stay_dates_valid')]

class Allocation(models.Model):
    reservation = models.ForeignKey(Reservation,on_delete=models.PROTECT,related_name='allocations')
    unit = models.ForeignKey(Unit,on_delete=models.PROTECT)
    start = models.DateField()
    end = models.DateField()
    rate = models.PositiveIntegerField(null=True,blank=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(end__gt=models.F('start')),name='allocation_dates_valid')]
        indexes = [models.Index(fields=['unit','start','end'])]

class Block(models.Model):
    unit = models.ForeignKey(Unit,on_delete=models.PROTECT)
    start = models.DateField()
    end = models.DateField()
    reason = models.CharField(max_length=250)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(end__gt=models.F('start')),name='block_dates_valid')]

class Invoice(models.Model):
    reservation = models.ForeignKey(Reservation,on_delete=models.PROTECT,related_name='invoices')
    kind = models.CharField(max_length=20,default='invoice')
    reference = models.ForeignKey('self',null=True,blank=True,on_delete=models.PROTECT)
    snapshot = models.JSONField(default=dict)
    total = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

class Charge(models.Model):
    unit = models.ForeignKey(Unit,on_delete=models.PROTECT,null=True,blank=True)
    reservation = models.ForeignKey(Reservation,on_delete=models.PROTECT,related_name='charges')
    service_date = models.DateField()
    description = models.CharField(max_length=200)
    net = models.BigIntegerField()
    tax = models.BigIntegerField(default=0)
    kind = models.CharField(max_length=20,default='room')
    invoice = models.ForeignKey(Invoice,on_delete=models.PROTECT,null=True,blank=True)

class Payment(models.Model):
    reservation = models.ForeignKey(Reservation,on_delete=models.PROTECT,related_name='payments')
    amount = models.BigIntegerField()  # negative is refund; never overwrite receipts
    method = models.CharField(max_length=30)
    reference = models.CharField(max_length=160,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)

class Audit(models.Model):
    property = models.ForeignKey(Property,on_delete=models.PROTECT)
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    action = models.CharField(max_length=60)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

class Operation(models.Model):
    property = models.ForeignKey(Property,on_delete=models.PROTECT)
    key = models.CharField(max_length=80)
    digest = models.CharField(max_length=64)
    result = models.JSONField(default=dict)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['property','key'],name='operation_unique')]

class Expense(models.Model):
    property = models.ForeignKey(Property,on_delete=models.PROTECT)
    reservation = models.ForeignKey(Reservation,on_delete=models.PROTECT,null=True,blank=True)
    amount = models.PositiveBigIntegerField()
    method = models.CharField(max_length=30)
    beneficiary = models.CharField(max_length=160)
    description = models.CharField(max_length=250)
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)

class Contract(models.Model):
    reservation = models.ForeignKey(Reservation,on_delete=models.PROTECT,related_name='contracts')
    snapshot = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)

class LedgerAccount(models.Model):
    property = models.ForeignKey(Property,on_delete=models.PROTECT)
    code = models.CharField(max_length=16)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=16,choices=[(x,x) for x in ['asset','liability','equity','revenue','expense']])
    class Meta:
        constraints=[models.UniqueConstraint(fields=['property','code'],name='ledger_account_code_unique')]

class PostedQuerySet(models.QuerySet):
    def update(self,**kwargs):raise ValidationError('القيود المنشورة لا تعدل؛ استخدم قيدًا عكسيًا')
    def delete(self):raise ValidationError('القيود المنشورة لا تحذف؛ استخدم قيدًا عكسيًا')
    def bulk_update(self,*args,**kwargs):raise ValidationError('القيود المنشورة لا تعدل')

class PostedModel(models.Model):
    objects=PostedQuerySet.as_manager()
    class Meta:abstract=True
    def save(self,*args,**kwargs):
        if not self._state.adding:raise ValidationError('القيود المنشورة لا تعدل؛ استخدم قيدًا عكسيًا')
        return super().save(*args,**kwargs)
    def delete(self,*args,**kwargs):raise ValidationError('القيود المنشورة لا تحذف؛ استخدم قيدًا عكسيًا')

class JournalEntry(PostedModel):
    property=models.ForeignKey(Property,on_delete=models.PROTECT)
    sequence=models.PositiveBigIntegerField()
    date=models.DateField()
    description=models.CharField(max_length=250)
    source=models.CharField(max_length=120)
    digest=models.CharField(max_length=64)
    currency=models.CharField(max_length=3)
    debit_total=models.PositiveBigIntegerField()
    credit_total=models.PositiveBigIntegerField()
    reversal_of=models.OneToOneField('self',null=True,blank=True,on_delete=models.PROTECT,related_name='reversal')
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['property','sequence'],name='journal_sequence_unique'),models.UniqueConstraint(fields=['property','source'],name='journal_source_unique'),models.CheckConstraint(condition=Q(debit_total=models.F('credit_total')) & Q(debit_total__gt=0),name='journal_totals_balanced')]

class JournalLine(PostedModel):
    entry=models.ForeignKey(JournalEntry,on_delete=models.PROTECT,related_name='lines')
    account=models.ForeignKey(LedgerAccount,on_delete=models.PROTECT)
    reservation=models.ForeignKey(Reservation,on_delete=models.PROTECT,null=True,blank=True)
    debit=models.PositiveBigIntegerField(default=0)
    credit=models.PositiveBigIntegerField(default=0)
    class Meta:
        constraints=[models.CheckConstraint(condition=(Q(debit__gt=0)&Q(credit=0))|(Q(credit__gt=0)&Q(debit=0)),name='journal_line_one_side')]

class LedgerOpening(PostedModel):
    property=models.OneToOneField(Property,on_delete=models.PROTECT,related_name='ledger_opening')
    start_date=models.DateField()
    reference=models.CharField(max_length=160)
    entry=models.OneToOneField(JournalEntry,on_delete=models.PROTECT,null=True,blank=True)
    unallocated_ack=models.BooleanField(default=False)
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)

class LedgerReconciliation(PostedModel):
    property=models.ForeignKey(Property,on_delete=models.PROTECT)
    account=models.ForeignKey(LedgerAccount,on_delete=models.PROTECT)
    date=models.DateField()
    reference=models.CharField(max_length=160)
    actual_balance=models.BigIntegerField()
    book_balance=models.BigIntegerField()
    difference=models.BigIntegerField()
    explanation=models.CharField(max_length=250,blank=True)
    digest=models.CharField(max_length=64)
    currency=models.CharField(max_length=3)
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['property','account','reference'],name='reconciliation_reference_unique'),models.CheckConstraint(condition=Q(difference=models.F('actual_balance')-models.F('book_balance')),name='reconciliation_difference_valid')]

class LedgerPeriodLock(PostedModel):
    property=models.ForeignKey(Property,on_delete=models.PROTECT)
    start=models.DateField()
    end=models.DateField()
    kind=models.CharField(max_length=8)
    reason=models.CharField(max_length=250)
    snapshot=models.JSONField(default=dict)
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.CheckConstraint(condition=Q(end__gt=models.F('start')),name='ledger_lock_positive_period')]

class LedgerPeriodReopen(PostedModel):
    lock=models.OneToOneField(LedgerPeriodLock,on_delete=models.PROTECT,related_name='reopening')
    reason=models.CharField(max_length=250)
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
