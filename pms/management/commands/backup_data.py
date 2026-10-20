import os
from pathlib import Path
from django.core.management import call_command
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help='Write a complete logical backup, including password hashes. Keep private.'
    def add_arguments(self,p):p.add_argument('output')
    def handle(self,*a,**opts):
        path=Path(opts['output']);path.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            call_command('dumpdata',exclude=['contenttypes','auth.permission','sessions'],natural_foreign=True,indent=2,stdout=f)
        self.stdout.write('Backup written: '+str(path))
