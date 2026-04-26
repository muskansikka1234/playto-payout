# EXPLAINER.md

> This document answers the five specific technical questions from the Playto challenge brief.

---

## 1. The Ledger — Balance Calculation Query

### The query (from `api/models.py`, `Merchant.get_balance()`):

```python
def get_balance(self):
    result = self.ledger_entries.aggregate(total=Sum('amount_paise'))
    return result['total'] or 0

def get_available_balance(self):
    total = self.get_balance()
    held = self.get_held_balance()
    return total - held

def get_held_balance(self):
    result = self.ledger_entries.filter(
        entry_type=LedgerEntry.EntryType.HOLD
    ).aggregate(total=Sum('amount_paise'))
    held = result['total'] or 0
    return abs(held)
```

This translates to SQL:
```sql
-- Total balance (credits - debits - holds + hold_releases)
SELECT SUM(amount_paise) FROM api_ledgerentry WHERE merchant_id = %s;

-- Held balance
SELECT SUM(amount_paise) FROM api_ledgerentry
WHERE merchant_id = %s AND entry_type = 'hold';
```

### Why model it this way?

**Ledger is append-only.** Every balance-changing event — customer payment, payout hold, payout settlement, hold release — creates a new row. Credits are stored as positive integers, debits/holds as negative integers. Balance is always `SUM(amount_paise)`.

This has three advantages over a mutable `balance` column:

1. **Correctness**: No read-modify-write cycle. A `balance` column requires: read value → compute new value → write back. Under concurrency, this is a race condition. The ledger is append-only: no race between reads.

2. **Auditability**: Every rupee movement is permanently recorded with a timestamp and description. If the balance looks wrong, you can query the ledger and trace exactly what happened.

3. **Verifiability**: The invariant `SUM(amount_paise) == displayed_balance` is checkable at any time against the raw data. A mutable balance field can be corrupted silently; the ledger cannot.

The `HOLD` entry type is the key to non-blocking payout creation: when a merchant requests a payout, we immediately write a negative HOLD entry. This reduces `available_balance` atomically with the payout creation (both in the same `transaction.atomic()` block with `SELECT FOR UPDATE`). The funds are effectively frozen before the bank call begins.

---

## 2. The Lock — Preventing Concurrent Overdraw

### Exact code (from `api/services.py`, `PayoutService.create_payout()`):

```python
@staticmethod
@transaction.atomic
def create_payout(merchant_id, amount_paise, bank_account_id, idempotency_key):
    # STEP 1: Acquire exclusive row lock on the merchant
    merchant = Merchant.objects.select_for_update().get(id=merchant_id)

    # STEP 2: Re-read the balance INSIDE the lock
    balance_result = merchant.ledger_entries.aggregate(total=Sum('amount_paise'))
    total_balance = balance_result['total'] or 0

    held_result = merchant.ledger_entries.filter(
        entry_type=LedgerEntry.EntryType.HOLD
    ).aggregate(total=Sum('amount_paise'))
    held_balance = abs(held_result['total'] or 0)

    available_balance = total_balance - held_balance

    # STEP 3: Check INSIDE the lock — not before it
    if amount_paise > available_balance:
        raise InsufficientBalanceError(...)

    # STEP 4: Write payout + HOLD atomically
    payout = Payout.objects.create(...)
    LedgerEntry.objects.create(amount_paise=-amount_paise, entry_type='hold', ...)
    # Lock releases on transaction commit
```

### The database primitive: `SELECT FOR UPDATE`

`Merchant.objects.select_for_update().get(id=merchant_id)` translates to:

```sql
SELECT * FROM api_merchant WHERE id = %s FOR UPDATE;
```

`FOR UPDATE` places an **exclusive row-level lock** on that merchant's row in PostgreSQL. Any other transaction that tries to `SELECT FOR UPDATE` the same row blocks — it waits at the database level until the first transaction commits or rolls back.

### Why this is the only correct approach

The naive approach (Python-level check) is broken:

```python
# WRONG — race condition
if merchant.available_balance >= amount_paise:  # Thread A: True. Thread B: True.
    merchant.available_balance -= amount_paise  # Both deduct. Overdraft.
```

Thread A and B both read 100₹, both see sufficient balance, both deduct 60₹. The merchant is now 20₹ overdrawn.

With `SELECT FOR UPDATE`:
- Thread A acquires the lock, reads 100₹, deducts 60₹, commits → merchant has 40₹
- Thread B was blocked at the lock. It now unblocks, re-reads 40₹, tries to deduct 60₹ → `InsufficientBalanceError`
- Exactly one payout succeeds, the other is rejected cleanly

The critical insight: **the balance read must happen inside the lock, not before it.** Any check done before acquiring the lock is stale by the time you write.

---

## 3. The Idempotency — How It Works

### How the system recognizes a seen key

```python
# From api/views.py, PayoutCreateView._get_or_create_idempotency_record()
@transaction.atomic
def _get_or_create_idempotency_record(merchant, key):
    try:
        record = IdempotencyKey.objects.get(merchant=merchant, key=key)
        return record, False   # seen before
    except IdempotencyKey.DoesNotExist:
        record = IdempotencyKey.objects.create(merchant=merchant, key=key)
        return record, True    # new
```

The `IdempotencyKey` table has a `UniqueConstraint(fields=['merchant', 'key'])`. If two requests arrive simultaneously with the same key, exactly one `INSERT` will succeed — the other will raise `IntegrityError`, which the view catches and re-fetches.

### The full idempotency flow

```
Request arrives with key K
│
├─ Key exists in DB?
│   ├─ Yes, expired (>24h)? → Delete it, treat as new
│   ├─ Yes, is_completed=True? → Return cached response_body + response_status
│   └─ Yes, is_completed=False? → Return 409 (still in-flight)
│
└─ No → Create IdempotencyKey row (is_completed=False)
         → Validate request body
         → Call PayoutService.create_payout()
         → Update IdempotencyKey: is_completed=True, store response_body + response_status
         → Return 201 response
```

### What happens if the first request is still in-flight when the second arrives

The first request creates the `IdempotencyKey` row with `is_completed=False` immediately on arrival — before the payout is created. The second request finds this row and gets a `409 Conflict` with the message "Request with this idempotency key is still in flight. Retry after a moment."

This is the correct behavior per Stripe's idempotency semantics: a key in-flight should block duplicate processing, not silently queue another one.

After the first request completes (payout created successfully), it sets `is_completed=True` and stores the serialized response. Any subsequent request with the same key returns that cached response immediately.

Keys are scoped per merchant — the unique constraint is on `(merchant_id, key)`, not just `key`. Merchant A's key `abc` does not conflict with Merchant B's key `abc`.

---

## 4. The State Machine — Blocking Illegal Transitions

### Where illegal transitions are blocked (from `api/models.py`):

```python
class Payout(models.Model):
    VALID_TRANSITIONS = {
        Status.PENDING:    {Status.PROCESSING},
        Status.PROCESSING: {Status.COMPLETED, Status.FAILED},
        Status.COMPLETED:  set(),   # terminal — no exits
        Status.FAILED:     set(),   # terminal — no exits
    }

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, set())

    def transition_to(self, new_status):
        if not self.can_transition_to(new_status):
            raise ValueError(
                f"Illegal state transition: {self.status} -> {new_status}. "
                f"Allowed: {self.VALID_TRANSITIONS.get(self.status, set())}"
            )
        self.status = new_status
```

`failed → completed` is blocked because `VALID_TRANSITIONS[Status.FAILED]` is an empty set. `transition_to(Status.COMPLETED)` on a failed payout immediately raises `ValueError`.

The service layer always calls `payout.transition_to(new_status)` before saving — it never sets `payout.status = X` directly. This means the state machine check is the only path to a status change:

```python
# In PayoutService.mark_completed():
payout = Payout.objects.select_for_update().get(id=payout_id)
payout.transition_to(Payout.Status.COMPLETED)  # raises ValueError if illegal
payout.save(update_fields=['status', 'updated_at'])
```

The lock (`select_for_update`) before the transition check also prevents two concurrent workers from both reading `processing` status and both trying to move to `completed` — only one will hold the lock during the check-and-write.

### Why the fund release on failure is atomic

```python
@transaction.atomic
def mark_failed(payout_id, reason=''):
    payout = Payout.objects.select_for_update().get(id=payout_id)
    payout.transition_to(Payout.Status.FAILED)    # state change
    payout.save(update_fields=['status', ...])

    LedgerEntry.objects.create(                   # hold release
        merchant=payout.merchant,
        amount_paise=payout.amount_paise,         # positive = returned
        entry_type=LedgerEntry.EntryType.HOLD_RELEASE,
        ...
    )
```

Both the status update and the `HOLD_RELEASE` ledger entry are in one `@transaction.atomic` block. If either fails, the entire transaction rolls back. This guarantees: a payout can never be marked failed without the funds being returned, and funds can never be returned without the payout being marked failed.

---

## 5. The AI Audit — One Specific Wrong Code Example

### What AI gave me (wrong):

When writing the balance check in `create_payout`, the AI's first draft was:

```python
@transaction.atomic
def create_payout(merchant_id, amount_paise, ...):
    merchant = Merchant.objects.get(id=merchant_id)  # ← no FOR UPDATE

    # Balance read BEFORE lock
    available = merchant.get_available_balance()
    if amount_paise > available:
        raise InsufficientBalanceError(...)

    payout = Payout.objects.create(...)
    LedgerEntry.objects.create(amount_paise=-amount_paise, ...)
```

### What I caught:

The `transaction.atomic` wrapper does wrap a transaction, but without `SELECT FOR UPDATE`, PostgreSQL uses **snapshot isolation** (the default `READ COMMITTED` level). Two concurrent transactions both read the merchant row at the same snapshot and both see the same balance. They both pass the `if amount_paise > available` check. Both then write their `HOLD` entries. The merchant is overdrawn.

`transaction.atomic` does **not** provide mutual exclusion on reads. It only ensures atomicity (all-or-nothing commit). Isolation level and locking are separate concerns.

### What I replaced it with:

```python
@transaction.atomic
def create_payout(merchant_id, amount_paise, ...):
    # FOR UPDATE: acquires exclusive row lock on merchant
    # Any concurrent transaction for the same merchant blocks here
    merchant = Merchant.objects.select_for_update().get(id=merchant_id)

    # Balance re-read INSIDE the lock — not stale
    balance_result = merchant.ledger_entries.aggregate(total=Sum('amount_paise'))
    ...
```

The key difference: `select_for_update()` adds `FOR UPDATE` to the SQL, which is a **pessimistic lock** at the database level — not a Python-level semaphore. The second concurrent transaction blocks at the PostgreSQL row lock, not at the Python `if` check. When it unblocks, it re-reads the already-reduced balance and correctly raises `InsufficientBalanceError`.

This is the most common mistake in payment code: conflating transaction atomicity with concurrency isolation. `@transaction.atomic` is not a mutex.
