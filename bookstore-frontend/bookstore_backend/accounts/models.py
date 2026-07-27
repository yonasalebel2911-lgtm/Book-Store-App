from django.db import models
from django.contrib.auth.models import AbstractUser

ROLE_CHOICES = [
    ('USER', 'User'),
    ('MERCHANT', 'Merchant'),
    ('ADMIN', 'Admin'),
]

STATUS_CHOICES = [
    ('ACTIVE', 'Active'),
    ('SUSPENDED', 'Suspended'),
    ('BANNED', 'Banned'),
]

class User(AbstractUser):
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='USER')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ACTIVE')
    phone = models.CharField(max_length=30, blank=True, default='')
    full_name = models.CharField(max_length=150, blank=True, default='')

    def __str__(self):
        return self.username


class UserAddress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    label = models.CharField(max_length=50, default='Home')
    full_name = models.CharField(max_length=100)
    street = models.CharField(max_length=200)
    address_line2 = models.CharField(max_length=200, blank=True, default='')
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    phone = models.CharField(max_length=30, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.label} - {self.full_name}"


class UserPreferences(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='preferences')
    email_notifications = models.BooleanField(default=True)
    newsletter = models.BooleanField(default=False)

    def __str__(self):
        return f"Preferences for {self.user.username}"
