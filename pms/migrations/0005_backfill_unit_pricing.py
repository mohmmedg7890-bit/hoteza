from django.db import migrations

def forward(apps,schema_editor):
    Allocation=apps.get_model('pms','Allocation');Charge=apps.get_model('pms','Charge')
    for a in Allocation.objects.filter(rate__isnull=True).select_related('reservation').iterator():
        a.rate=a.reservation.rate;a.save(update_fields=['rate'])
    for c in Charge.objects.filter(unit__isnull=True,kind__in=['room','room_reversal','discount','discount_reversal']).iterator():
        choices=list(Allocation.objects.filter(reservation_id=c.reservation_id,start__lte=c.service_date,end__gt=c.service_date).values_list('unit_id',flat=True)[:2])
        if len(choices)==1:c.unit_id=choices[0];c.save(update_fields=['unit'])

class Migration(migrations.Migration):
    dependencies=[('pms','0004_allocation_rate_charge_unit_property_contract_terms_and_more')]
    operations=[migrations.RunPython(forward,migrations.RunPython.noop)]
