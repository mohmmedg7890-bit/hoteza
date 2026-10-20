from django.core.management import call_command
from django.core.management.base import BaseCommand,CommandError
from django.contrib.auth import get_user_model
from pms.models import Property

class Command(BaseCommand):
    help='Restore only into an empty migrated database. Never overwrites live data.'
    def add_arguments(self,p):p.add_argument('input');p.add_argument('--confirm-empty-database',action='store_true')
    def handle(self,*a,**opts):
        if not opts['confirm_empty_database'] or Property.objects.exists() or get_user_model().objects.exists():raise CommandError('Restore requires an empty database and --confirm-empty-database.')
        call_command('loaddata',opts['input'])
