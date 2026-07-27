from django.db import models
from django.conf import settings
from django.utils import timezone


class Order(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PAID', 'Paid'),
        ('SHIPPED', 'Shipped'),
        ('DELIVERED', 'Delivered'),
        ('CONFIRMED', 'Confirmed'),
        ('CANCELLED', 'Cancelled'),
        ('FAILED', 'Failed'),
        ('REFUNDED', 'Refunded'),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='PENDING')
    delivered_at = models.DateTimeField(blank=True, null=True)
    confirmed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def delivery_deadline(self):
        """5-day window after merchant marks delivered."""
        if self.delivered_at:
            return self.delivered_at + timezone.timedelta(days=5)
        return None

    @property
    def is_deadline_passed(self):
        if self.delivery_deadline:
            return timezone.now() > self.delivery_deadline
        return False

    def __str__(self):
        return f"Order {self.id} by {self.user.username}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    book = models.ForeignKey('books.Book', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.quantity} x {self.book.title}"


class Payment(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment')
    tx_ref = models.CharField(max_length=64, unique=True)
    chapa_reference = models.CharField(max_length=128, blank=True, null=True)
    payment_method = models.CharField(max_length=32, default='CHAPA')
    address = models.TextField()
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment for Order {self.order.id}"


class Payout(models.Model):
    PAYOUT_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('RELEASED', 'Released'),
        ('HELD', 'Held'),
    ]
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payout')
    merchant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payouts')
    order_amount = models.DecimalField(max_digits=10, decimal_places=2)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=10.00)
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2)
    payout_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=PAYOUT_STATUS_CHOICES, default='PENDING')
    released_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payout #{self.id} for Order {self.order.id} → {self.merchant.username}"


class PayoutRequest(models.Model):
    PAYOUT_REQUEST_STATUS = [
        ('REQUESTED', 'Requested'),
        ('CONFIRMED', 'Confirmed'),
        ('REJECTED', 'Rejected'),
    ]
    merchant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payout_requests')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=PAYOUT_REQUEST_STATUS, default='REQUESTED')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"PayoutRequest #{self.id} by {self.merchant.username} - ${self.amount}"


class SupportMessage(models.Model):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='support_messages')
    subject = models.CharField(max_length=200)
    message = models.TextField()
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Support: {self.subject} from {self.sender.username}"


class SiteSettings(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField(default='')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Site Settings'

    def __str__(self):
        return self.key
