"""
API Views for Playto Payout Engine.

Key design decisions:
- Idempotency handled at the view layer before service layer
- Merchant ID passed via URL; in production this would come from JWT auth
- All errors return structured JSON with error codes
"""
import logging
import uuid

from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Merchant, Payout, LedgerEntry, IdempotencyKey
from .serializers import (
    MerchantSerializer, PayoutSerializer,
    CreatePayoutSerializer, LedgerEntrySerializer, BankAccountSerializer
)
from .services import PayoutService, InsufficientBalanceError

logger = logging.getLogger(__name__)


class MerchantListView(APIView):
    def get(self, request):
        merchants = Merchant.objects.prefetch_related('bank_accounts').all()
        serializer = MerchantSerializer(merchants, many=True)
        return Response(serializer.data)


class MerchantDetailView(APIView):
    def get(self, request, merchant_id):
        try:
            merchant = Merchant.objects.prefetch_related('bank_accounts').get(id=merchant_id)
        except Merchant.DoesNotExist:
            return Response({'error': 'Merchant not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = MerchantSerializer(merchant)
        return Response(serializer.data)


class MerchantLedgerView(APIView):
    def get(self, request, merchant_id):
        try:
            merchant = Merchant.objects.get(id=merchant_id)
        except Merchant.DoesNotExist:
            return Response({'error': 'Merchant not found'}, status=status.HTTP_404_NOT_FOUND)

        entries = merchant.ledger_entries.all()[:50]
        serializer = LedgerEntrySerializer(entries, many=True)
        return Response({
            'entries': serializer.data,
            'available_balance_paise': merchant.get_available_balance(),
            'held_balance_paise': merchant.get_held_balance(),
            'total_balance_paise': merchant.get_balance(),
        })


class PayoutCreateView(APIView):
    """
    POST /api/v1/payouts
    Headers: X-Idempotency-Key: <uuid>  (required)
             X-Merchant-ID: <uuid>       (required, normally from JWT)

    Idempotency flow:
    1. Check if we've seen this (merchant, key) pair before.
    2. If yes and completed → return cached response.
    3. If yes and in-flight → return 409 with retry hint.
    4. If no → proceed with payout creation.
    """

    def post(self, request):
        # --- Extract headers ---
        idempotency_key = request.headers.get('X-Idempotency-Key', '').strip()
        merchant_id = request.headers.get('X-Merchant-ID', '').strip()

        if not idempotency_key:
            return Response(
                {'error': 'X-Idempotency-Key header is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not merchant_id:
            return Response(
                {'error': 'X-Merchant-ID header is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate UUIDs
        try:
            uuid.UUID(idempotency_key)
            uuid.UUID(merchant_id)
        except ValueError:
            return Response(
                {'error': 'X-Idempotency-Key and X-Merchant-ID must be valid UUIDs.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate merchant exists
        try:
            merchant = Merchant.objects.get(id=merchant_id)
        except Merchant.DoesNotExist:
            return Response({'error': 'Merchant not found.'}, status=status.HTTP_404_NOT_FOUND)

        # --- Idempotency check ---
        try:
            idempotency_record, created = self._get_or_create_idempotency_record(merchant, idempotency_key)
        except IntegrityError:
            # Race: two requests hit simultaneously, other one won the create
            # Fetch the winner's record
            try:
                idempotency_record = IdempotencyKey.objects.get(merchant=merchant, key=idempotency_key)
                created = False
            except IdempotencyKey.DoesNotExist:
                return Response({'error': 'Idempotency conflict. Retry.'}, status=status.HTTP_409_CONFLICT)

        if not created:
            # We've seen this key before
            if idempotency_record.is_expired():
                # Expired — delete and treat as new
                idempotency_record.delete()
                idempotency_record = IdempotencyKey.objects.create(merchant=merchant, key=idempotency_key)
            elif idempotency_record.is_completed:
                # Return exact same cached response
                return Response(
                    idempotency_record.response_body,
                    status=idempotency_record.response_status
                )
            else:
                # In-flight (first request not yet finished)
                return Response(
                    {'error': 'Request with this idempotency key is still in flight. Retry after a moment.'},
                    status=status.HTTP_409_CONFLICT
                )

        # --- Validate request body ---
        serializer = CreatePayoutSerializer(data=request.data)
        if not serializer.is_valid():
            # Cleanup the idempotency record since request was invalid
            idempotency_record.delete()
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        amount_paise = serializer.validated_data['amount_paise']
        bank_account_id = serializer.validated_data['bank_account_id']

        # --- Create payout ---
        try:
            payout = PayoutService.create_payout(
                merchant_id=merchant_id,
                amount_paise=amount_paise,
                bank_account_id=str(bank_account_id),
                idempotency_key=idempotency_key,
            )
        except InsufficientBalanceError as e:
            idempotency_record.delete()
            return Response(
                {'error': str(e), 'code': 'insufficient_balance'},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        except ValueError as e:
            idempotency_record.delete()
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            idempotency_record.delete()
            logger.exception(f"Unexpected error creating payout: {e}")
            return Response({'error': 'Internal server error.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # --- Queue for processing ---
        from .tasks import process_payout
        process_payout.delay(str(payout.id))

        # --- Cache the response ---
        response_data = PayoutSerializer(payout).data
        response_status_code = status.HTTP_201_CREATED

        idempotency_record.payout = payout
        idempotency_record.response_body = response_data
        idempotency_record.response_status = response_status_code
        idempotency_record.is_completed = True
        idempotency_record.save(update_fields=['payout', 'response_body', 'response_status', 'is_completed'])

        return Response(response_data, status=response_status_code)

    @staticmethod
    @transaction.atomic
    def _get_or_create_idempotency_record(merchant, key):
        """
        Atomically get or create an idempotency record.
        Returns (record, created). Raises IntegrityError on concurrent duplicate.
        """
        try:
            record = IdempotencyKey.objects.get(merchant=merchant, key=key)
            return record, False
        except IdempotencyKey.DoesNotExist:
            record = IdempotencyKey.objects.create(merchant=merchant, key=key)
            return record, True


class PayoutListView(APIView):
    def get(self, request):
        merchant_id = request.headers.get('X-Merchant-ID', '').strip()
        if not merchant_id:
            return Response({'error': 'X-Merchant-ID header required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            merchant = Merchant.objects.get(id=merchant_id)
        except Merchant.DoesNotExist:
            return Response({'error': 'Merchant not found.'}, status=status.HTTP_404_NOT_FOUND)

        payouts = Payout.objects.filter(merchant=merchant).select_related('bank_account')[:50]
        serializer = PayoutSerializer(payouts, many=True)
        return Response(serializer.data)


class PayoutDetailView(APIView):
    def get(self, request, payout_id):
        try:
            payout = Payout.objects.get(id=payout_id)
        except Payout.DoesNotExist:
            return Response({'error': 'Payout not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = PayoutSerializer(payout)
        return Response(serializer.data)


class HealthCheckView(APIView):
    def get(self, request):
        return Response({'status': 'ok', 'service': 'playto-payout-engine'})
