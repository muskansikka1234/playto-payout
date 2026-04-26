import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Merchant',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='BankAccount',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('merchant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bank_accounts', to='api.merchant')),
                ('account_holder_name', models.CharField(max_length=255)),
                ('account_number', models.CharField(max_length=50)),
                ('ifsc_code', models.CharField(max_length=11)),
                ('bank_name', models.CharField(max_length=255)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='Payout',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('merchant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payouts', to='api.merchant')),
                ('bank_account', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payouts', to='api.bankaccount')),
                ('amount_paise', models.BigIntegerField()),
                ('status', models.CharField(
                    choices=[('pending', 'Pending'), ('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed')],
                    default='pending', max_length=20
                )),
                ('retry_count', models.IntegerField(default=0)),
                ('idempotency_key', models.CharField(db_index=True, max_length=255)),
                ('failure_reason', models.CharField(blank=True, max_length=500)),
                ('processing_started_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='LedgerEntry',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('merchant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='ledger_entries', to='api.merchant')),
                ('amount_paise', models.BigIntegerField()),
                ('entry_type', models.CharField(
                    choices=[('credit', 'Credit'), ('debit', 'Debit'), ('hold', 'Hold'), ('hold_release', 'Hold Release')],
                    max_length=20
                )),
                ('description', models.CharField(blank=True, max_length=500)),
                ('reference_id', models.UUIDField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='IdempotencyKey',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('merchant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='idempotency_keys', to='api.merchant')),
                ('key', models.CharField(max_length=255)),
                ('response_status', models.IntegerField(blank=True, null=True)),
                ('response_body', models.JSONField(blank=True, null=True)),
                ('payout', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='api.payout')),
                ('is_completed', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        # Indexes
        migrations.AddIndex(
            model_name='ledgerentry',
            index=models.Index(fields=['merchant', '-created_at'], name='ledger_merchant_date_idx'),
        ),
        migrations.AddIndex(
            model_name='ledgerentry',
            index=models.Index(fields=['merchant', 'entry_type'], name='ledger_merchant_type_idx'),
        ),
        migrations.AddIndex(
            model_name='ledgerentry',
            index=models.Index(fields=['reference_id'], name='ledger_reference_idx'),
        ),
        migrations.AddIndex(
            model_name='payout',
            index=models.Index(fields=['merchant', 'status'], name='payout_merchant_status_idx'),
        ),
        migrations.AddIndex(
            model_name='payout',
            index=models.Index(fields=['status', 'processing_started_at'], name='payout_status_time_idx'),
        ),
        migrations.AddIndex(
            model_name='payout',
            index=models.Index(fields=['merchant', 'idempotency_key'], name='payout_merchant_ikey_idx'),
        ),
        migrations.AddIndex(
            model_name='idempotencykey',
            index=models.Index(fields=['merchant', 'key'], name='ikey_merchant_key_idx'),
        ),
        migrations.AddIndex(
            model_name='idempotencykey',
            index=models.Index(fields=['created_at'], name='ikey_created_idx'),
        ),
        # Unique constraints
        migrations.AddConstraint(
            model_name='payout',
            constraint=models.UniqueConstraint(fields=['merchant', 'idempotency_key'], name='unique_idempotency_key_per_merchant'),
        ),
        migrations.AddConstraint(
            model_name='idempotencykey',
            constraint=models.UniqueConstraint(fields=['merchant', 'key'], name='unique_key_per_merchant'),
        ),
    ]
