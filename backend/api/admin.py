from django.contrib import admin
from .models import Merchant, BankAccount, LedgerEntry, Payout, IdempotencyKey


@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'created_at']
    search_fields = ['name', 'email']


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ['merchant', 'bank_name', 'account_number', 'ifsc_code', 'is_active']
    list_filter = ['is_active', 'bank_name']


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ['merchant', 'entry_type', 'amount_paise', 'description', 'created_at']
    list_filter = ['entry_type']
    search_fields = ['merchant__name', 'description']


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ['id', 'merchant', 'amount_paise', 'status', 'retry_count', 'created_at']
    list_filter = ['status']
    search_fields = ['merchant__name']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(admin.ModelAdmin):
    list_display = ['merchant', 'key', 'is_completed', 'created_at']
    list_filter = ['is_completed']
