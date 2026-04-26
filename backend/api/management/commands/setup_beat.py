"""
Sets up the Celery Beat periodic task schedule in the database.
Run once after migrations: python manage.py setup_beat
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Configure Celery Beat periodic tasks for payout processing.'

    def handle(self, *args, **options):
        from django_celery_beat.models import PeriodicTask, IntervalSchedule
        import json

        # Every 15 seconds: retry stuck payouts
        schedule_15s, _ = IntervalSchedule.objects.get_or_create(
            every=15, period=IntervalSchedule.SECONDS
        )
        PeriodicTask.objects.update_or_create(
            name='Retry stuck payouts',
            defaults={
                'interval': schedule_15s,
                'task': 'api.tasks.retry_stuck_payouts',
                'args': json.dumps([]),
            }
        )

        # Every 30 seconds: sweep pending payouts
        schedule_30s, _ = IntervalSchedule.objects.get_or_create(
            every=30, period=IntervalSchedule.SECONDS
        )
        PeriodicTask.objects.update_or_create(
            name='Process pending payouts',
            defaults={
                'interval': schedule_30s,
                'task': 'api.tasks.process_pending_payouts',
                'args': json.dumps([]),
            }
        )

        self.stdout.write(self.style.SUCCESS(
            'Beat schedule configured:\n'
            '  - retry_stuck_payouts: every 15s\n'
            '  - process_pending_payouts: every 30s'
        ))
