from django.urls import path
from .views import (
    MerchantListView, MerchantDetailView, MerchantLedgerView,
    PayoutCreateView, PayoutListView, PayoutDetailView,
    HealthCheckView,
)

urlpatterns = [
    path('health/', HealthCheckView.as_view(), name='health-check'),
    path('merchants/', MerchantListView.as_view(), name='merchant-list'),
    path('merchants/<uuid:merchant_id>/', MerchantDetailView.as_view(), name='merchant-detail'),
    path('merchants/<uuid:merchant_id>/ledger/', MerchantLedgerView.as_view(), name='merchant-ledger'),
    path('payouts/', PayoutCreateView.as_view(), name='payout-create'),
    path('payouts/list/', PayoutListView.as_view(), name='payout-list'),
    path('payouts/<uuid:payout_id>/', PayoutDetailView.as_view(), name='payout-detail'),
]
