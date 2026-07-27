from rest_framework import serializers
from .models import Book, WishlistItem

class BookSerializer(serializers.ModelSerializer):
    merchant_username = serializers.CharField(source='merchant.username', read_only=True)
    image_full_url = serializers.SerializerMethodField()

    class Meta:
        model = Book
        fields = [
            'id', 'title', 'author', 'description', 'category', 'price',
            'stock', 'image', 'image_url', 'image_full_url',
            'merchant', 'merchant_username', 'approved', 'created_at',
        ]
        read_only_fields = ['merchant', 'approved']

    def get_image_full_url(self, obj):
        request = self.context.get('request')
        if obj.image and hasattr(obj.image, 'url'):
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return obj.image_url or None


class WishlistItemSerializer(serializers.ModelSerializer):
    book = BookSerializer(read_only=True)
    book_id = serializers.IntegerField(source='book.id', read_only=True)

    class Meta:
        model = WishlistItem
        fields = ['id', 'book_id', 'book', 'created_at']