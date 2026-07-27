from rest_framework import serializers
from .models import Order, OrderItem, Payment, Payout, PayoutRequest, SupportMessage, SiteSettings


class OrderItemSerializer(serializers.ModelSerializer):
    book_title = serializers.CharField(source='book.title', read_only=True)
    book_price = serializers.DecimalField(source='book.price', max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'book', 'book_title', 'book_price', 'quantity']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    user_username = serializers.CharField(source='user.username', read_only=True)
    delivery_deadline = serializers.DateTimeField(read_only=True)
    is_deadline_passed = serializers.BooleanField(read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'user', 'user_username', 'items', 'total_amount',
            'status', 'delivered_at', 'confirmed_at',
            'delivery_deadline', 'is_deadline_passed', 'created_at',
        ]
        read_only_fields = ['user', 'total_amount', 'status', 'created_at']


class PaymentSerializer(serializers.ModelSerializer):
    order_id = serializers.IntegerField(source='order.id', read_only=True)

    class Meta:
        model = Payment
        fields = ['id', 'order', 'order_id', 'tx_ref', 'chapa_reference', 'payment_method', 'address', 'payment_status', 'created_at']
        read_only_fields = ['order', 'tx_ref', 'chapa_reference', 'payment_status', 'created_at']


class PayoutSerializer(serializers.ModelSerializer):
    merchant_username = serializers.CharField(source='merchant.username', read_only=True)
    order_id = serializers.IntegerField(source='order.id', read_only=True)
    order_status = serializers.CharField(source='order.status', read_only=True)

    class Meta:
        model = Payout
        fields = [
            'id', 'order', 'order_id', 'order_status',
            'merchant', 'merchant_username',
            'order_amount', 'commission_rate', 'commission_amount', 'payout_amount',
            'status', 'released_at', 'created_at',
        ]
        read_only_fields = ['__all__']


class PayoutRequestSerializer(serializers.ModelSerializer):
    merchant_username = serializers.CharField(source='merchant.username', read_only=True)

    class Meta:
        model = PayoutRequest
        fields = ['id', 'merchant', 'merchant_username', 'amount', 'status', 'created_at']
        read_only_fields = ['id', 'merchant', 'merchant_username', 'created_at']


class SupportMessageSerializer(serializers.ModelSerializer):
    sender_username = serializers.CharField(source='sender.username', read_only=True)
    sender_role = serializers.CharField(source='sender.role', read_only=True)

    class Meta:
        model = SupportMessage
        fields = ['id', 'sender', 'sender_username', 'sender_role', 'subject', 'message', 'read', 'created_at']
        read_only_fields = ['id', 'sender', 'sender_username', 'sender_role', 'created_at']


class SiteSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteSettings
        fields = ['id', 'key', 'value', 'updated_at']