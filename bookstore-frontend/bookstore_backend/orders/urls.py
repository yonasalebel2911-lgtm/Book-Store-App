from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    CheckoutView,
    VerifyPaymentView,
    ChapaWebhookView,
    PaidOrdersView,
    ChapaPayView,
    OrderViewSet,
    PaymentViewSet,
    PayoutListView,
    PayoutReleaseView,
    AdminFinanceView,
    MerchantEarningsView,
    PayoutRequestListCreateView,
    PayoutRequestUpdateView,
    SupportMessageListCreateView,
    SupportMessageUpdateView,
    SiteSettingsListView,
)

router = DefaultRouter()
router.register(r'orders', OrderViewSet)
router.register(r'payments', PaymentViewSet)

urlpatterns = [
    path('pay/', ChapaPayView.as_view(), name='chapa_pay'),
    path('verify/', VerifyPaymentView.as_view(), name='chapa_verify'),
    path('orders/paid/', PaidOrdersView.as_view(), name='paid_orders'),
    path('payments/checkout/', CheckoutView.as_view(), name='chapa_checkout'),
    path('payments/verify/', VerifyPaymentView.as_view(), name='chapa_verify_legacy'),
    path('payments/webhook/', ChapaWebhookView.as_view(), name='chapa_webhook'),
    # Payout / finance endpoints
    path('payouts/', PayoutListView.as_view(), name='payout_list'),
    path('payouts/<int:payout_id>/release/', PayoutReleaseView.as_view(), name='payout_release'),
    path('admin/finance/', AdminFinanceView.as_view(), name='admin_finance'),
    path('merchant/earnings/', MerchantEarningsView.as_view(), name='merchant_earnings'),
    # Payout requests
    path('payout-requests/', PayoutRequestListCreateView.as_view(), name='payout_request_list'),
    path('payout-requests/<int:pk>/', PayoutRequestUpdateView.as_view(), name='payout_request_detail'),
    # Support messages
    path('support-messages/', SupportMessageListCreateView.as_view(), name='support_message_list'),
    path('support-messages/<int:pk>/', SupportMessageUpdateView.as_view(), name='support_message_detail'),
    # Site settings
    path('site-settings/', SiteSettingsListView.as_view(), name='site_settings'),
] + router.urls