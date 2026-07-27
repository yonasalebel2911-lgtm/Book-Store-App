from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from .models import Cart, CartItem
from .serializers import CartSerializer, CartItemSerializer
from books.models import Book


class CartView(APIView):
    """GET the current user's cart."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        serializer = CartSerializer(cart)
        return Response(serializer.data)


class CartItemView(APIView):
    """POST to add an item, PATCH/DELETE to update/remove by item id."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        product_id = request.data.get('product_id')
        quantity = int(request.data.get('quantity', 1))

        book = get_object_or_404(Book, id=product_id)

        item, created = CartItem.objects.get_or_create(
            cart=cart, product=book,
            defaults={'quantity': quantity}
        )
        if not created:
            item.quantity += quantity
            item.save()

        # Return the full cart so the frontend can sync state
        serializer = CartSerializer(cart)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def patch(self, request, item_id=None):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        item = get_object_or_404(CartItem, id=item_id, cart=cart)
        quantity = int(request.data.get('quantity', 1))
        item.quantity = max(1, quantity)
        item.save()
        serializer = CartSerializer(cart)
        return Response(serializer.data)

    def delete(self, request, item_id=None):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        item = get_object_or_404(CartItem, id=item_id, cart=cart)
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ClearCartView(APIView):
    """POST to clear all items from cart."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        cart.items.all().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
