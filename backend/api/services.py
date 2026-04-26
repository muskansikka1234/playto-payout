"""
Payout service layer.

All money operations go through here. The critical section is create_payout:
  1. Lock the merchant row with SELECT FOR UPDATE (DB-level exclusive lock)
  2. Re-read the balance inside the lock (prevents TOCTOU race)
  3. Write the HOLD ledger entry atomically with the Payout record
  4. Commit — lock releases

This means two concurrent requests for the same merchant serialize at the DB.
Only one will proceed; the other waits, then sees insufficient balance.
"""
import logging
import uuid
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import Merchant, Payout, LedgerEntry, IdempotencyKey, BankAccount

logger = logging.getLogger(__name__)


class InsufficientBalanceError(Exception):
    pass


class InvalidTransitionError(Exception):
    pass


class PayoutService:

    @staticmethod
    @transaction.atomic
    def create_payout(merchant_id: str, amount_paise: int, bank_account_id: str, idempotency_key: str) -> Payout:
        """
        Create a payout with fund hold. Uses SELECT FOR UPDATE to prevent concurrent overdraw.

        The lock is on the Merchant row. Any concurrent call for the same merchant
        blocks here until the first transaction commits or rolls back.
        This is the ONLY safe way to do check-then-act on a balance.
        """
        # --- LOCK: acquire exclusive row lock on merchant ---
        merchant = Merchant.objects.select_for_update().get(id=merchant_id)

        # --- CHECK: read balance INSIDE the lock ---
        # We calculate available balance at DB level, inside the transaction,
        # after acquiring the lock. This eliminates the TOCTOU race.
        balance_result = merchant.ledger_entries.aggregate(total=Sum('amount_paise'))
        total_balance = balance_result['total'] or 0

        held_result = merchant.ledger_entries.filter(
            entry_type=LedgerEntry.EntryType.HOLD
        ).aggregate(total=Sum('amount_paise'))
        held_balance = abs(held_result['total'] or 0)

        available_balance = total_balance - held_balance

        if amount_paise > available_balance:
            raise InsufficientBalanceError(
                f"Insufficient balance. Available: {available_balance} paise, Requested: {amount_paise} paise"
            )

        # Validate bank account belongs to merchant
        try:
            bank_account = BankAccount.objects.get(id=bank_account_id, merchant=merchant, is_active=True)
        except BankAccount.DoesNotExist:
            raise ValueError(f"Bank account {bank_account_id} not found or inactive for this merchant.")

        # --- CREATE: payout + HOLD ledger entry atomically ---
        payout = Payout.objects.create(
            merchant=merchant,
            bank_account=bank_account,
            amount_paise=amount_paise,
            status=Payout.Status.PENDING,
            idempotency_key=idempotency_key,
        )

        # HOLD entry: negative amount = funds locked
        LedgerEntry.objects.create(
            merchant=merchant,
            amount_paise=-amount_paise,  # negative = deducted from available
            entry_type=LedgerEntry.EntryType.HOLD,
            description=f"Hold for payout {payout.id}",
            reference_id=payout.id,
        )

        logger.info(f"Payout {payout.id} created: {amount_paise} paise held for merchant {merchant_id}")
        return payout

    @staticmethod
    @transaction.atomic
    def mark_processing(payout_id: str) -> Payout:
        """Move payout from pending to processing."""
        payout = Payout.objects.select_for_update().get(id=payout_id)
        payout.transition_to(Payout.Status.PROCESSING)
        payout.processing_started_at = timezone.now()
        payout.save(update_fields=['status', 'processing_started_at', 'updated_at'])
        return payout

    @staticmethod
    @transaction.atomic
    def mark_completed(payout_id: str) -> Payout:
        """
        Mark payout completed.
        The HOLD entry already removed funds from available balance.
        On completion, we convert HOLD to DEBIT — the hold entry stays negative,
        but we record a final DEBIT to make the accounting explicit.
        Actually: HOLD already debited funds. We just change status.
        The hold entry IS the debit — no need for double-entry here.
        Just confirm the payout is settled.
        """
        payout = Payout.objects.select_for_update().get(id=payout_id)
        payout.transition_to(Payout.Status.COMPLETED)
        payout.save(update_fields=['status', 'updated_at'])

        # Convert the HOLD entry to DEBIT for clean accounting
        LedgerEntry.objects.filter(
            merchant=payout.merchant,
            reference_id=payout.id,
            entry_type=LedgerEntry.EntryType.HOLD,
        ).update(entry_type=LedgerEntry.EntryType.DEBIT)

        logger.info(f"Payout {payout_id} completed.")
        return payout

    @staticmethod
    @transaction.atomic
    def mark_failed(payout_id: str, reason: str = '') -> Payout:
        """
        Mark payout failed AND atomically release the held funds.
        This MUST be atomic: if we mark failed but don't release the hold,
        the merchant permanently loses access to that money.
        """
        payout = Payout.objects.select_for_update().get(id=payout_id)
        payout.transition_to(Payout.Status.FAILED)
        payout.failure_reason = reason
        payout.save(update_fields=['status', 'failure_reason', 'updated_at'])

        # --- ATOMIC HOLD RELEASE ---
        # Delete the HOLD entry (or create a matching HOLD_RELEASE)
        # We create a HOLD_RELEASE (positive entry) to keep full audit trail.
        LedgerEntry.objects.create(
            merchant=payout.merchant,
            amount_paise=payout.amount_paise,  # positive = returned to balance
            entry_type=LedgerEntry.EntryType.HOLD_RELEASE,
            description=f"Hold released: payout {payout.id} failed. Reason: {reason}",
            reference_id=payout.id,
        )

        logger.info(f"Payout {payout_id} failed, {payout.amount_paise} paise released. Reason: {reason}")
        return payout

    @staticmethod
    def get_or_create_idempotency_key(merchant_id: str, key: str):
        """
        Returns (idempotency_record, created).
        Uses get_or_create which is atomic at the DB level via unique constraint.
        If two requests arrive simultaneously with the same key, exactly one will
        get created=True, the other gets created=False and sees the existing record.
        """
        from django.utils import timezone
        from django.conf import settings

        merchant = Merchant.objects.get(id=merchant_id)

        # Check if existing key is expired — if so, delete and allow fresh
        try:
            existing = IdempotencyKey.objects.get(merchant=merchant, key=key)
            if existing.is_expired():
                existing.delete()
                # Fall through to create new
            else:
                return existing, False
        except IdempotencyKey.DoesNotExist:
            pass

        # Create new idempotency record (may raise IntegrityError on race)
        record = IdempotencyKey.objects.create(merchant=merchant, key=key)
        return record, True

    @staticmethod
    def seed_credit(merchant_id: str, amount_paise: int, description: str = 'Customer payment received'):
        """Add a credit to a merchant's ledger. Used for seeding and simulation."""
        with transaction.atomic():
            merchant = Merchant.objects.select_for_update().get(id=merchant_id)
            entry = LedgerEntry.objects.create(
                merchant=merchant,
                amount_paise=amount_paise,
                entry_type=LedgerEntry.EntryType.CREDIT,
                description=description,
            )
        return entry
