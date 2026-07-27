from django.db import models
from django.conf import settings

CATEGORY_CHOICES = [
    ('fiction', 'Fiction'),
    ('non-fiction', 'Non-Fiction'),
    ('academic', 'Academic'),
    ('children', 'Children'),
    ('business', 'Business'),
    ('history', 'History'),
    ('politics', 'Politics'),
]

class Book(models.Model):
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255, default='Unknown')
    description = models.TextField(blank=True, default='')
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='fiction')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to='books/', blank=True, null=True)
    image_url = models.URLField(max_length=500, blank=True, null=True)
    merchant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='books')
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class WishlistItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wishlist_items')
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='wishlisted_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'book']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} ♡ {self.book.title}"