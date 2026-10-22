from django.core.management.base import BaseCommand
from django.utils import timezone
from pms.models import Reservation,Membership
from pms.services import perform
class Command(BaseCommand):
    help='Run due opted-in extensions. Schedule every minute for operation while browsers are closed.'
    def handle(self,*args,**options):
        for r in Reservation.objects.filter(status='checked_in',auto_extend=True,departure__lte=timezone.localdate()):
            member=Membership.objects.filter(property=r.property,role='owner').select_related('user').order_by('id').first()
            if not member:continue
            try:
                perform(member.user,r.property_id,'auto_extend',{'id':r.pk},f'auto-{r.pk}-{r.departure}')
                self.stdout.write(f'Extended reservation {r.pk}')
            except Exception as exc:
                self.stderr.write(f'Reservation {r.pk}: {type(exc).__name__}: {exc}')
