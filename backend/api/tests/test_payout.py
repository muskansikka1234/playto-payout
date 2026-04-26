"""
Tests for the Playto Payout Engine.

Critical tests:
1. Concurrency: Two concurrent 60₹ payouts on a 100₹ balance → exactly one succeeds
2. Idempotency: Same key twice → same response, no duplicate payout
3. State machine: Illegal transitions raise ValueError
4. Ledger integrity: Balance = sum of all ledger entries
"""
import threading
import uuid
from unittest.mock import patch

from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from rest_framework.test import APIClient

from api.models import Merchant, BankAccount, LedgerEntry, Payout, IdempotencyKey
from api.services import PayoutService, InsufficientBalanceError


def create_merchant_with_balance(name, email, balance_paise):
    """Helper: create a merchant and seed a credit."""
    merchant = Merchant.objects.create(name=name, email=email)
    bank_account = BankAccount.objects.create(
        merchant=merchant,
        account_holder_name=name,
        account_number='1234567890',
        ifsc_code='HDFC0001234',
        bank_name='HDFC Bank',
    )
    PayoutService.seed_credit(str(merchant.id), balance_paise, 'Test credit')
    return merchant, bank_account


class TestLedgerIntegrity(TestCase):
    """Balance must always equal sum of all ledger entries."""

    def test_balance_equals_sum_of_ledger_entries(self):
        merchant, bank_account = create_merchant_with_balance(
            'Test Merchant', 'test@example.com', 100000  # ₹1000
        )
        self.assertEqual(merchant.get_balance(), 100000)

        # Create a payout (places a HOLD)
        payout = PayoutService.create_payout(
            merchant_id=str(merchant.id),
            amount_paise=50000,
            bank_account_id=str(bank_account.id),
            idempotency_key=str(uuid.uuid4()),
        )

        # Total balance unchanged (hold doesn't change total, only available)
        self.assertEqual(merchant.get_balance(), 50000)   # 100000 - 50000 hold
        self.assertEqual(merchant.get_held_balance(), 50000)
        self.assertEqual(merchant.get_available_balance(), 50000)

        # On success: convert HOLD → DEBIT, total balance should still be 50000
        PayoutService.mark_processing(str(payout.id))
        PayoutService.mark_completed(str(payout.id))
        merchant.refresh_from_db()
        self.assertEqual(merchant.get_balance(), 50000)
        self.assertEqual(merchant.get_held_balance(), 0)
        self.assertEqual(merchant.get_available_balance(), 50000)

    def test_failed_payout_returns_funds(self):
        merchant, bank_account = create_merchant_with_balance(
            'Return Merchant', 'return@example.com', 100000
        )
        payout = PayoutService.create_payout(
            merchant_id=str(merchant.id),
            amount_paise=60000,
            bank_account_id=str(bank_account.id),
            idempotency_key=str(uuid.uuid4()),
        )
        PayoutService.mark_processing(str(payout.id))
        PayoutService.mark_failed(str(payout.id), reason='Bank rejected')

        # Funds should be fully returned
        self.assertEqual(merchant.get_available_balance(), 100000)
        self.assertEqual(merchant.get_held_balance(), 0)
        self.assertEqual(merchant.get_balance(), 100000)


class TestConcurrency(TransactionTestCase):
    """
    Two concurrent 60₹ payout requests on a 100₹ balance.
    Exactly one must succeed, the other must be rejected.

    TransactionTestCase is used (not TestCase) because we need real DB transactions
    to test SELECT FOR UPDATE behavior — TestCase wraps everything in one transaction
    which prevents testing row-level locking.
    """

    def test_concurrent_payouts_exactly_one_succeeds(self):
        merchant, bank_account = create_merchant_with_balance(
            'Concurrent Merchant', 'concurrent@example.com', 100000  # ₹1000
        )

        results = []
        errors = []

        def attempt_payout():
            try:
                payout = PayoutService.create_payout(
                    merchant_id=str(merchant.id),
                    amount_paise=60000,  # ₹600 — more than half
                    bank_account_id=str(bank_account.id),
                    idempotency_key=str(uuid.uuid4()),  # different keys
                )
                results.append(('success', payout.id))
            except InsufficientBalanceError as e:
                errors.append(('insufficient_balance', str(e)))
            except Exception as e:
                errors.append(('error', str(e)))

        # Fire two threads simultaneously
        t1 = threading.Thread(target=attempt_payout)
        t2 = threading.Thread(target=attempt_payout)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        total_outcomes = len(results) + len(errors)
        self.assertEqual(total_outcomes, 2, "Both requests should have completed")
        self.assertEqual(len(results), 1, "Exactly one payout should succeed")
        self.assertEqual(len(errors), 1, "Exactly one payout should fail with InsufficientBalance")
        self.assertIn('insufficient_balance', errors[0][0])

        # Verify balance integrity
        merchant.refresh_from_db()
        self.assertEqual(
            merchant.get_available_balance(), 40000,  # 100000 - 60000 held
            "Available balance should be ₹400 (100000 - 60000 held)"
        )

    def test_cannot_overdraw_with_sequential_requests(self):
        merchant, bank_account = create_merchant_with_balance(
            'Sequential Merchant', 'sequential@example.com', 50000  # ₹500
        )

        # First payout ₹400 — should succeed
        payout1 = PayoutService.create_payout(
            merchant_id=str(merchant.id),
            amount_paise=40000,
            bank_account_id=str(bank_account.id),
            idempotency_key=str(uuid.uuid4()),
        )
        self.assertIsNotNone(payout1)

        # Second payout ₹200 — should fail (only ₹100 left)
        with self.assertRaises(InsufficientBalanceError):
            PayoutService.create_payout(
                merchant_id=str(merchant.id),
                amount_paise=20000,
                bank_account_id=str(bank_account.id),
                idempotency_key=str(uuid.uuid4()),
            )


class TestIdempotency(TransactionTestCase):
    """
    Same idempotency key sent twice must return identical response, no duplicate payout.
    """

    def setUp(self):
        self.client = APIClient()
        self.merchant, self.bank_account = create_merchant_with_balance(
            'Idempotent Merchant', 'idempotent@example.com', 500000
        )

    def test_same_key_returns_same_response(self):
        idempotency_key = str(uuid.uuid4())

        headers = {
            'HTTP_X_IDEMPOTENCY_KEY': idempotency_key,
            'HTTP_X_MERCHANT_ID': str(self.merchant.id),
        }
        body = {
            'amount_paise': 10000,
            'bank_account_id': str(self.bank_account.id),
        }

        # First request
        response1 = self.client.post('/api/v1/payouts/', body, format='json', **headers)
        self.assertEqual(response1.status_code, 201)

        # Second request — same key
        response2 = self.client.post('/api/v1/payouts/', body, format='json', **headers)
        self.assertEqual(response2.status_code, 201)

        # Responses must be identical
        self.assertEqual(response1.data['id'], response2.data['id'])

        # Only one payout created
        payout_count = Payout.objects.filter(
            merchant=self.merchant,
            idempotency_key=idempotency_key
        ).count()
        self.assertEqual(payout_count, 1, "Idempotent request must not create duplicate payout")

    def test_different_keys_create_different_payouts(self):
        body = {
            'amount_paise': 10000,
            'bank_account_id': str(self.bank_account.id),
        }

        response1 = self.client.post('/api/v1/payouts/', body, format='json', **{
            'HTTP_X_IDEMPOTENCY_KEY': str(uuid.uuid4()),
            'HTTP_X_MERCHANT_ID': str(self.merchant.id),
        })
        response2 = self.client.post('/api/v1/payouts/', body, format='json', **{
            'HTTP_X_IDEMPOTENCY_KEY': str(uuid.uuid4()),
            'HTTP_X_MERCHANT_ID': str(self.merchant.id),
        })

        self.assertEqual(response1.status_code, 201)
        self.assertEqual(response2.status_code, 201)
        self.assertNotEqual(response1.data['id'], response2.data['id'])

    def test_missing_idempotency_key_returns_400(self):
        response = self.client.post('/api/v1/payouts/', {
            'amount_paise': 10000,
            'bank_account_id': str(self.bank_account.id),
        }, format='json', **{'HTTP_X_MERCHANT_ID': str(self.merchant.id)})

        self.assertEqual(response.status_code, 400)


class TestStateMachine(TestCase):
    """State machine must reject illegal transitions."""

    def setUp(self):
        self.merchant, self.bank_account = create_merchant_with_balance(
            'State Merchant', 'state@example.com', 100000
        )

    def _make_payout(self):
        return PayoutService.create_payout(
            merchant_id=str(self.merchant.id),
            amount_paise=10000,
            bank_account_id=str(self.bank_account.id),
            idempotency_key=str(uuid.uuid4()),
        )

    def test_valid_transitions_succeed(self):
        payout = self._make_payout()
        self.assertEqual(payout.status, Payout.Status.PENDING)

        PayoutService.mark_processing(str(payout.id))
        payout.refresh_from_db()
        self.assertEqual(payout.status, Payout.Status.PROCESSING)

        PayoutService.mark_completed(str(payout.id))
        payout.refresh_from_db()
        self.assertEqual(payout.status, Payout.Status.COMPLETED)

    def test_cannot_go_backwards_completed_to_pending(self):
        payout = self._make_payout()
        PayoutService.mark_processing(str(payout.id))
        PayoutService.mark_completed(str(payout.id))

        # Try to go backwards — must raise
        with self.assertRaises(ValueError):
            payout.refresh_from_db()
            payout.transition_to(Payout.Status.PENDING)

    def test_cannot_go_failed_to_completed(self):
        payout = self._make_payout()
        PayoutService.mark_processing(str(payout.id))
        PayoutService.mark_failed(str(payout.id), 'test failure')

        with self.assertRaises(ValueError):
            payout.refresh_from_db()
            payout.transition_to(Payout.Status.COMPLETED)

    def test_cannot_skip_processing(self):
        payout = self._make_payout()
        with self.assertRaises(ValueError):
            payout.transition_to(Payout.Status.COMPLETED)

    def test_completed_payout_cannot_transition_anywhere(self):
        payout = self._make_payout()
        PayoutService.mark_processing(str(payout.id))
        PayoutService.mark_completed(str(payout.id))

        for bad_status in [Payout.Status.PENDING, Payout.Status.PROCESSING, Payout.Status.FAILED]:
            with self.assertRaises(ValueError):
                payout.refresh_from_db()
                payout.transition_to(bad_status)
