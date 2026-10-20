import os
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

class Command(BaseCommand):
    help = 'Initialize an empty trial database from private environment variables; never reset existing accounts.'

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        if User.objects.exists():
            self.stdout.write('Existing accounts retained. Bootstrap skipped.')
            return
        username = os.getenv('INITIAL_ADMIN_USERNAME', 'owner').strip()
        password = os.getenv('INITIAL_ADMIN_PASSWORD', '')
        if not username or len(username) > 150 or len(password) < 12:
            raise CommandError('Set INITIAL_ADMIN_USERNAME and a private INITIAL_ADMIN_PASSWORD of at least 12 characters.')
        user = User(username=username)
        try:
            user.full_clean(exclude=['password'])
            validate_password(password, user=user)
        except ValidationError:
            raise CommandError('Initial account settings do not pass validation. Use a unique username and strong password.')
        if os.getenv('BOOTSTRAP_DEMO', '0') == '1':
            previous = os.environ.get('DEMO_PASSWORD')
            os.environ['DEMO_PASSWORD'] = password
            try:
                call_command('seed_demo', username=username, stdout=self.stdout)
            finally:
                if previous is None:
                    os.environ.pop('DEMO_PASSWORD', None)
                else:
                    os.environ['DEMO_PASSWORD'] = previous
        else:
            User.objects.create_superuser(username=username, password=password, email=os.getenv('INITIAL_ADMIN_EMAIL', ''))
            self.stdout.write('Initial owner created. Complete property setup after sign-in.')
