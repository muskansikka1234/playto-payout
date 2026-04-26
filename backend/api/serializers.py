from rest_framework import serializers
from .models import Merchant, BankAccount, LedgerEntry, Payout


class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = ['id', 'account_holder_name', 'account_number', 'ifsc_code', 'bank_name', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class LedgerEntrySerializer(serializers.ModelSerializer):
    amount_inr = serializers.SerializerMethodField()

    class Meta:
        model = LedgerEntry
        fields = ['id', 'amount_paise', 'amount_inr', 'entry_type', 'description', 'reference_id', 'created_at']

    def get_amount_inr(self, obj):
        return obj.amount_paise / 100


class PayoutSerializer(serializers.ModelSerializer):
    bank_account = BankAccountSerializer(read_only=True)
    bank_account_id = serializers.UUIDField(write_only=True)
    amount_inr = serializers.SerializerMethodField()

    class Meta:
        model = Payout
        fields = [
            'id', 'amount_paise', 'amount_inr', 'status',
            'bank_account', 'bank_account_id',
            'retry_count', 'failure_reason',
            'created_at', 'updated_at', 'processing_started_at'
        ]
        read_only_fields = ['id', 'status', 'retry_count', 'failure_reason', 'created_at', 'updated_at']

    def get_amount_inr(self, obj):
        return obj.amount_paise / 100


class CreatePayoutSerializer(serializers.Serializer):
    amount_paise = serializers.IntegerField(min_value=100)  # min 1 rupee
    bank_account_id = serializers.UUIDField()

    def validate_amount_paise(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be positive.")
        return value


class MerchantSerializer(serializers.ModelSerializer):
    available_balance_paise = serializers.SerializerMethodField()
    held_balance_paise = serializers.SerializerMethodField()
    total_balance_paise = serializers.SerializerMethodField()
    bank_accounts = BankAccountSerializer(many=True, read_only=True)

    class Meta:
        model = Merchant
        fields = [
            'id', 'name', 'email',
            'available_balance_paise', 'held_balance_paise', 'total_balance_paise',
            'bank_accounts', 'created_at'
        ]

    def get_total_balance_paise(self, obj):
        return obj.get_balance()

    def get_available_balance_paise(self, obj):
        return obj.get_available_balance()

    def get_held_balance_paise(self, obj):
        return obj.get_held_balance()
