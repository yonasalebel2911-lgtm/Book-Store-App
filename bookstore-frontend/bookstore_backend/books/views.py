from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Book, WishlistItem
from .serializers import BookSerializer, WishlistItemSerializer


class IsAdminOrSuperuser(permissions.BasePermission):
    """Allow access only to users with role=ADMIN or is_superuser."""
    def has_permission(self, request, view):
        return (
            request.user and request.user.is_authenticated and
            (request.user.is_superuser or getattr(request.user, 'role', '').upper() == 'ADMIN')
        )


class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.all()
    serializer_class = BookSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['title', 'author', 'category', 'description']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        if self.action in ['approve', 'reject']:
            return [IsAdminOrSuperuser()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return Book.objects.filter(approved=True)
        if getattr(user, 'role', '') == 'MERCHANT':
            return Book.objects.filter(merchant=user)
        if getattr(user, 'role', '') == 'ADMIN' or user.is_superuser:
            return Book.objects.all()
        return Book.objects.filter(approved=True)

    def perform_create(self, serializer):
        # Merchant creates book — always starts as unapproved
        serializer.save(merchant=self.request.user, approved=False)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        book = self.get_object()
        book.approved = True
        book.save()
        return Response(BookSerializer(book).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        book = self.get_object()
        book.approved = False
        book.save()
        return Response(BookSerializer(book).data)


# ─── Wishlist ─────────────────────────────────────────────────

class WishlistView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        items = WishlistItem.objects.filter(user=request.user).select_related('book')
        return Response(WishlistItemSerializer(items, many=True).data)

    def post(self, request):
        book_id = request.data.get('book_id')
        if not book_id:
            return Response({'error': 'book_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        book = Book.objects.filter(id=book_id).first()
        if not book:
            return Response({'error': 'Book not found'}, status=status.HTTP_404_NOT_FOUND)
        item, created = WishlistItem.objects.get_or_create(user=request.user, book=book)
        if not created:
            return Response({'message': 'Already in wishlist'}, status=status.HTTP_200_OK)
        return Response(WishlistItemSerializer(item).data, status=status.HTTP_201_CREATED)

    def delete(self, request):
        book_id = request.data.get('book_id') or request.query_params.get('book_id')
        if not book_id:
            return Response({'error': 'book_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        WishlistItem.objects.filter(user=request.user, book_id=book_id).delete()
        return Response({'message': 'Removed from wishlist'}, status=status.HTTP_204_NO_CONTENT)