import uuid
from django.db import models
from django.db.models import Sum
from django.utils import timezone


class Merchant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.email})"

    def get_balance(self):
        """
        Balance is derived purely from ledger entries at the DB level.
        Never calculated in Python on fetched rows — this is a single aggregation query.
        Credits are positive (money in), debits are negative (money out / held).
        """
        result = self.ledger_entries.aggregate(total=Sum('amount_paise'))
        return result['total'] or 0

    def get_available_balance(self):
        """Available = total balance minus held amounts (pending payouts)."""
        total = self.get_balance()
        held = self.get_held_balance()
        return total - held

    def get_held_balance(self):
        """Held = sum of all pending payout debit holds."""
        result = self.ledger_entries.filter(
            entry_type=LedgerEntry.EntryType.HOLD
        ).aggregate(total=Sum('amount_paise'))
        # Holds are stored as negative amounts, return as positive for display
        held = result['total'] or 0
        return abs(held)

    class Meta:
        ordering = ['name']


class BankAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name='bank_accounts')
    account_holder_name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=50)
    ifsc_code = models.CharField(max_length=11)
    bank_name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.bank_name} ****{self.account_number[-4:]}"

    class Meta:
        ordering = ['-created_at']


class LedgerEntry(models.Model):
    """
    Immutable ledger. Every balance change is a new row.
    Credits are positive integers (customer payments arriving).
    Debits are negative integers (payout settled or hold placed).
    HOLD entries are negative: funds locked for a pending payout.
    HOLD_RELEASE entries are positive: funds returned on payout failure.
    DEBIT entries are negative: funds permanently out on payout success.

    This model is the source of truth. The balance is always Sum(amount_paise).
    """

    class EntryType(models.TextChoices):
        CREDIT = 'credit', 'Credit'         # +amount: customer payment received
        DEBIT = 'debit', 'Debit'             # -amount: payout settled successfully
        HOLD = 'hold', 'Hold'               # -amount: funds held for pending payout
        HOLD_RELEASE = 'hold_release', 'Hold Release'  # +amount: hold reversed on failure

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name='ledger_entries')
    amount_paise = models.BigIntegerField()  # positive = credit, negative = debit/hold
    entry_type = models.CharField(max_length=20, choices=EntryType.choices)
    description = models.CharField(max_length=500, blank=True)
    reference_id = models.UUIDField(null=True, blank=True)  # links to Payout.id
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['merchant', '-created_at']),
            models.Index(fields=['merchant', 'entry_type']),
            models.Index(fields=['reference_id']),
        ]

    def __str__(self):
        return f"{self.entry_type} {self.amount_paise} paise for {self.merchant}"


class Payout(models.Model):
    """
    State machine: pending -> processing -> completed
                                         -> failed
    No backwards transitions allowed. Enforced at the model level.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    # Allowed forward transitions only
    VALID_TRANSITIONS = {
        Status.PENDING: {Status.PROCESSING},
        Status.PROCESSING: {Status.COMPLETED, Status.FAILED},
        Status.COMPLETED: set(),
        Status.FAILED: set(),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name='payouts')
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name='payouts')
    amount_paise = models.BigIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    retry_count = models.IntegerField(default=0)
    idempotency_key = models.CharField(max_length=255, db_index=True)
    failure_reason = models.CharField(max_length=500, blank=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['merchant', 'status']),
            models.Index(fields=['status', 'processing_started_at']),
            models.Index(fields=['merchant', 'idempotency_key']),
        ]
        # Unique constraint: one idempotency key per merchant
        constraints = [
            models.UniqueConstraint(
                fields=['merchant', 'idempotency_key'],
                name='unique_idempotency_key_per_merchant'
            )
        ]

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, set())

    def transition_to(self, new_status):
        """Enforce state machine. Raises ValueError on illegal transition."""
        if not self.can_transition_to(new_status):
            raise ValueError(
                f"Illegal state transition: {self.status} -> {new_status}. "
                f"Allowed: {self.VALID_TRANSITIONS.get(self.status, set())}"
            )
        self.status = new_status

    def __str__(self):
        return f"Payout {self.id} [{self.status}] {self.amount_paise} paise"


class IdempotencyKey(models.Model):
    """
    Tracks idempotency keys with their cached responses.
    Scoped per merchant. Expires after 24 hours.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name='idempotency_keys')
    key = models.CharField(max_length=255)
    response_status = models.IntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    payout = models.ForeignKey(Payout, on_delete=models.SET_NULL, null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['merchant', 'key'],
                name='unique_key_per_merchant'
            )
        ]
        indexes = [
            models.Index(fields=['merchant', 'key']),
            models.Index(fields=['created_at']),
        ]

    def is_expired(self):
        from django.conf import settings
        expiry_hours = getattr(settings, 'IDEMPOTENCY_KEY_EXPIRY_HOURS', 24)
        return timezone.now() > self.created_at + timezone.timedelta(hours=expiry_hours)

    def __str__(self):
        return f"IdempotencyKey {self.key} for {self.merchant}"
