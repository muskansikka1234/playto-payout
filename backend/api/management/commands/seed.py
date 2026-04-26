"""
Seed script: creates 3 merchants with bank accounts and credit history.
Run: python manage.py seed
"""
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from api.models import Merchant, BankAccount, LedgerEntry, Payout, IdempotencyKey
from api.services import PayoutService


class Command(BaseCommand):
    help = 'Seed the database with merchants, bank accounts, and ledger entries.'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true', help='Clear existing data first')

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Clearing existing data...')
            IdempotencyKey.objects.all().delete()
            LedgerEntry.objects.all().delete()
            Payout.objects.all().delete()
            BankAccount.objects.all().delete()
            Merchant.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Cleared.'))

        # --- Merchant 1: Arjun Singh - Freelance Developer ---
        arjun, _ = Merchant.objects.get_or_create(
            email='arjun@example.com',
            defaults={'name': 'Arjun Singh'}
        )
        BankAccount.objects.get_or_create(
            merchant=arjun,
            account_number='12345678901234',
            defaults={
                'account_holder_name': 'Arjun Singh',
                'ifsc_code': 'HDFC0001234',
                'bank_name': 'HDFC Bank',
            }
        )
        # Credit history: 3 payments
        credits_arjun = [
            (150000, 'Client payment: Logo design project - Acme Corp USA'),
            (250000, 'Client payment: Web development - StartupX USA'),
            (75000,  'Client payment: UI review - DesignCo UK'),
        ]
        for amount, desc in credits_arjun:
            if not LedgerEntry.objects.filter(merchant=arjun, description=desc).exists():
                PayoutService.seed_credit(str(arjun.id), amount, desc)

        self.stdout.write(f'Merchant: {arjun.name} — balance: {arjun.get_balance()} paise')

        # --- Merchant 2: Priya Sharma - Digital Marketing Agency ---
        priya, _ = Merchant.objects.get_or_create(
            email='priya@example.com',
            defaults={'name': 'Priya Sharma'}
        )
        BankAccount.objects.get_or_create(
            merchant=priya,
            account_number='98765432109876',
            defaults={
                'account_holder_name': 'Priya Sharma',
                'ifsc_code': 'ICIC0005678',
                'bank_name': 'ICICI Bank',
            }
        )
        credits_priya = [
            (500000, 'Client payment: SEO campaign Q1 - GlobalBrand UK'),
            (300000, 'Client payment: Social media management - TechFirm USA'),
            (180000, 'Client payment: Content writing - MediaHouse Canada'),
            (420000, 'Client payment: PPC management - EcomStore USA'),
        ]
        for amount, desc in credits_priya:
            if not LedgerEntry.objects.filter(merchant=priya, description=desc).exists():
                PayoutService.seed_credit(str(priya.id), amount, desc)

        self.stdout.write(f'Merchant: {priya.name} — balance: {priya.get_balance()} paise')

        # --- Merchant 3: Rahul Tech Solutions - SaaS Company ---
        rahul, _ = Merchant.objects.get_or_create(
            email='rahul@example.com',
            defaults={'name': 'Rahul Tech Solutions'}
        )
        BankAccount.objects.get_or_create(
            merchant=rahul,
            account_number='11223344556677',
            defaults={
                'account_holder_name': 'Rahul Kumar',
                'ifsc_code': 'SBIN0009012',
                'bank_name': 'State Bank of India',
            }
        )
        credits_rahul = [
            (1000000, 'Subscription revenue: Enterprise plan - MegaCorp USA'),
            (250000,  'Subscription revenue: Pro plan x5 - Various USA clients'),
            (150000,  'One-time setup: Custom integration - DataFlow Australia'),
        ]
        for amount, desc in credits_rahul:
            if not LedgerEntry.objects.filter(merchant=rahul, description=desc).exists():
                PayoutService.seed_credit(str(rahul.id), amount, desc)

        self.stdout.write(f'Merchant: {rahul.name} — balance: {rahul.get_balance()} paise')

        self.stdout.write(self.style.SUCCESS('\nSeed complete! Summary:'))
        self.stdout.write(f'  Arjun Singh:         ₹{arjun.get_balance()/100:.2f} available')
        self.stdout.write(f'  Priya Sharma:        ₹{priya.get_balance()/100:.2f} available')
        self.stdout.write(f'  Rahul Tech:          ₹{rahul.get_balance()/100:.2f} available')
        self.stdout.write(f'\nMerchant IDs:')
        self.stdout.write(f'  Arjun: {arjun.id}')
        self.stdout.write(f'  Priya: {priya.id}')
        self.stdout.write(f'  Rahul: {rahul.id}')
