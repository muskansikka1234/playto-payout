"""
Celery tasks for payout processing.

Bank simulation:
  - 70% success
  - 20% failure
  - 10% hang (stays in processing, triggering retry logic)

Retry logic:
  - Payouts stuck in processing > 30s are picked up by the retry task
  - Exponential backoff: 10s, 20s, 40s
  - After 3 attempts, move to failed and release funds
"""
import logging
import random
import time

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import Payout
from .services import PayoutService, InvalidTransitionError

logger = logging.getLogger(__name__)

PROCESSING_TIMEOUT = getattr(settings, 'PAYOUT_PROCESSING_TIMEOUT_SECONDS', 30)
MAX_RETRIES = getattr(settings, 'PAYOUT_MAX_RETRY_ATTEMPTS', 3)


def simulate_bank_response():
    """
    Simulate bank API response.
    Returns: 'success', 'failure', or 'hang'
    """
    roll = random.random()
    if roll < 0.70:
        return 'success'
    elif roll < 0.90:
        return 'failure'
    else:
        return 'hang'


@shared_task(bind=True, max_retries=0, name='api.tasks.process_payout')
def process_payout(self, payout_id: str):
    """
    Process a single payout.
    Moves pending -> processing, simulates bank call, then moves to completed/failed.
    On 'hang', we do nothing — the stuck-payout sweeper will retry it.
    """
    logger.info(f"[process_payout] Starting payout {payout_id}")

    try:
        payout = Payout.objects.get(id=payout_id)
    except Payout.DoesNotExist:
        logger.error(f"[process_payout] Payout {payout_id} not found.")
        return

    # Only process pending payouts
    if payout.status != Payout.Status.PENDING:
        logger.warning(f"[process_payout] Payout {payout_id} is in state {payout.status}, skipping.")
        return

    try:
        PayoutService.mark_processing(payout_id)
    except (InvalidTransitionError, ValueError) as e:
        logger.error(f"[process_payout] Cannot move to processing: {e}")
        return

    # Simulate network delay to the bank
    time.sleep(random.uniform(0.5, 2.0))

    outcome = simulate_bank_response()
    logger.info(f"[process_payout] Payout {payout_id} bank outcome: {outcome}")

    if outcome == 'success':
        try:
            PayoutService.mark_completed(payout_id)
            logger.info(f"[process_payout] Payout {payout_id} COMPLETED.")
        except Exception as e:
            logger.error(f"[process_payout] Failed to mark completed: {e}")

    elif outcome == 'failure':
        try:
            PayoutService.mark_failed(payout_id, reason='Bank rejected the transaction')
            logger.info(f"[process_payout] Payout {payout_id} FAILED, funds released.")
        except Exception as e:
            logger.error(f"[process_payout] Failed to mark failed: {e}")

    elif outcome == 'hang':
        # Do nothing — payout stays in 'processing'
        # The retry_stuck_payouts task will pick it up after PROCESSING_TIMEOUT seconds
        logger.info(f"[process_payout] Payout {payout_id} HUNG in processing.")


@shared_task(name='api.tasks.retry_stuck_payouts')
def retry_stuck_payouts():
    """
    Periodic task: find payouts stuck in 'processing' for > PROCESSING_TIMEOUT seconds.
    Retry up to MAX_RETRIES times with exponential backoff.
    After max retries, mark as failed and release funds.

    This task should run every 15 seconds via Celery Beat.
    """
    timeout_threshold = timezone.now() - timezone.timedelta(seconds=PROCESSING_TIMEOUT)

    stuck_payouts = Payout.objects.filter(
        status=Payout.Status.PROCESSING,
        processing_started_at__lt=timeout_threshold,
    )

    for payout in stuck_payouts:
        logger.info(f"[retry_stuck_payouts] Found stuck payout {payout.id}, retry_count={payout.retry_count}")

        if payout.retry_count >= MAX_RETRIES:
            # Exhausted retries — fail the payout and release funds
            try:
                PayoutService.mark_failed(
                    str(payout.id),
                    reason=f'Timed out after {MAX_RETRIES} retries'
                )
                logger.info(f"[retry_stuck_payouts] Payout {payout.id} exceeded max retries, marked FAILED.")
            except Exception as e:
                logger.error(f"[retry_stuck_payouts] Could not fail payout {payout.id}: {e}")
        else:
            # Reset to pending so process_payout can pick it up again
            # Use exponential backoff by scheduling with countdown
            backoff_seconds = (2 ** payout.retry_count) * 10  # 10s, 20s, 40s

            # Update retry count and reset status to PENDING atomically
            from django.db import transaction
            with transaction.atomic():
                # Re-fetch with lock
                p = Payout.objects.select_for_update().get(id=payout.id)
                if p.status != Payout.Status.PROCESSING:
                    continue  # Already handled by another worker
                p.retry_count += 1
                p.status = Payout.Status.PENDING
                p.processing_started_at = None
                p.failure_reason = f'Retry {p.retry_count}/{MAX_RETRIES} after timeout'
                p.save(update_fields=['retry_count', 'status', 'processing_started_at', 'failure_reason', 'updated_at'])

            # Schedule retry with backoff
            process_payout.apply_async(args=[str(payout.id)], countdown=backoff_seconds)
            logger.info(
                f"[retry_stuck_payouts] Payout {payout.id} queued for retry {payout.retry_count}/{MAX_RETRIES} "
                f"in {backoff_seconds}s"
            )


@shared_task(name='api.tasks.process_pending_payouts')
def process_pending_payouts():
    """
    Periodic sweeper: pick up any pending payouts that weren't queued
    (e.g., after a worker restart). Runs every 30 seconds.
    """
    pending = Payout.objects.filter(status=Payout.Status.PENDING)
    for payout in pending:
        process_payout.delay(str(payout.id))
        logger.info(f"[process_pending_payouts] Queued payout {payout.id}")
