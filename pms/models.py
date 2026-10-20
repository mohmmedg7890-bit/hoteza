from django.db import models
from django.conf import settings
from django.db.models import Q

class Property(models.Model):
    name = models.CharField(max_length=160)
    address = models.CharField(max_length=300, blank=True)
    tax_number = models.CharField(max_length=30, blank=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
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

class Reservation(models.Model):
    property = models.ForeignKey(Property,on_delete=models.PROTECT)
    guest = models.ForeignKey(Guest,on_delete=models.PROTECT)
    arrival = models.DateField()
    departure = models.DateField()
    persons = models.PositiveIntegerField(default=1)
    rate = models.PositiveIntegerField()
    status = models.CharField(max_length=20,default='confirmed')
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
