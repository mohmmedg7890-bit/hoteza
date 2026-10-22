import os,secrets
from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from pms.models import Property, Membership, Unit, Guest, Reservation, Allocation, Payment
from pms.services import nightly

class Command(BaseCommand):
    help='Create isolated synthetic demo data; never resets an existing installation.'
    def add_arguments(self,p):
        p.add_argument('--username',default='demo-owner')
    @transaction.atomic
    def handle(self,*a,**opts):
        if Property.objects.exists() or get_user_model().objects.filter(username=opts['username']).exists():raise CommandError('Database already initialized; refusing to overwrite.')
        password=os.getenv('DEMO_PASSWORD') or secrets.token_urlsafe(18)
        owner=get_user_model().objects.create_user(username=opts['username'],password=password,email='demo@example.invalid',is_staff=True,is_superuser=True)
        today=timezone.localdate()
        for j in range(2):
            p=Property.objects.create(name=['Hoteza — منشأة العرض','Hoteza — اختبار العزل'][j],address='بيانات وهمية فقط',tax_rate=15,subscription_until=today+timedelta(days=30))
            Membership.objects.create(user=owner,property=p,role='owner')
            units=[]
            for i in range(20 if j==0 else 10):
                units.append(Unit.objects.create(property=p,number=str(101+i),kind=['استوديو','غرفة وصالة','غرفتان وصالة'][i%3],floor='الأول' if i<10 else 'الثاني',capacity=[2,3,5][i%3],rate=[13000,15000,26000][i%3]))
            for i in range(6):
                g=Guest.objects.create(property=p,name='نزيل تجريبي '+['الأول','الثاني','الثالث','الرابع','الخامس','السادس'][i],phone='0500000000',email='demo@example.com',region='عسير',city='أبها',street='عنوان تجريبي')
                start=today+timedelta(days=i-2);end=start+timedelta(days=3)
                status='checked_in' if i<2 else 'confirmed'
                r=Reservation.objects.create(property=p,guest=g,arrival=start,departure=end,persons=2,rate=units[i].rate,status=status,source='استقبال',checked_in_at=timezone.now() if i<2 else None)
                Allocation.objects.create(reservation=r,unit=units[i],start=start,end=end);nightly(r,start,end,r.rate)
                Payment.objects.create(reservation=r,amount=10000,method='نقد',user=owner,reference='دفعة تجريبية')
        self.stdout.write(self.style.SUCCESS(f'Created 2 properties / 30 units. Username: {owner.username}'))
        if not os.getenv('DEMO_PASSWORD'):self.stdout.write('Generated temporary password: '+password)
