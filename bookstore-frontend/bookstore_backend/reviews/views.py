from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from .models import Review
from .serializers import ReviewSerializer

class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer
    pagination_class = None

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = Review.objects.all()
        book_id = self.request.query_params.get('book')
        if book_id:
            qs = qs.filter(book_id=book_id)
        elif self.request.user.is_authenticated and getattr(self.request.user, 'role', '').upper() == 'MERCHANT':
            qs = qs.filter(book__merchant=self.request.user)
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def reply(self, request, pk=None):
        """Merchant replies to a review on their book."""
        review = self.get_object()
        user = request.user
        role = getattr(user, 'role', '').upper()

        # Only the merchant who owns the book can reply
        if role != 'MERCHANT' or review.book.merchant != user:
            return Response({'error': 'Only the book merchant can reply.'}, status=status.HTTP_403_FORBIDDEN)

        reply_text = request.data.get('reply', '').strip()
        if not reply_text:
            return Response({'error': 'Reply text is required.'}, status=status.HTTP_400_BAD_REQUEST)

        review.merchant_reply = reply_text
        review.merchant_reply_at = timezone.now()
        review.save()

        return Response(ReviewSerializer(review).data)