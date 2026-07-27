from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import BookViewSet, WishlistView

router = DefaultRouter()
router.register(r'books', BookViewSet)

urlpatterns = [
    path('wishlist/', WishlistView.as_view(), name='wishlist'),
] + router.urls