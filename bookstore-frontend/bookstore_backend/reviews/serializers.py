from rest_framework import serializers
from .models import Review

class ReviewSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source='user.username', read_only=True)
    book_title = serializers.CharField(source='book.title', read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'user', 'user_username', 'book', 'book_title', 'rating', 'comment',
                  'merchant_reply', 'merchant_reply_at', 'created_at']
        read_only_fields = ['user', 'merchant_reply', 'merchant_reply_at']