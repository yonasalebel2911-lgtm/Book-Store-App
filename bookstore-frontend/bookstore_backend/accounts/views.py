from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from django.contrib.auth import authenticate
from django.db.models import Sum, Count
from .models import User, UserAddress, UserPreferences
from .serializers import (
    UserSerializer, RegisterSerializer, AdminUserSerializer,
    UserAddressSerializer, UserPreferencesSerializer,
)


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

class LoginView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = TokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.user
        user_data = UserSerializer(user).data

        return Response({
            'access': serializer.validated_data['access'],
            'refresh': serializer.validated_data['refresh'],
            'user': user_data,
            'role': user.role,
            'is_superuser': user.is_superuser,
            'is_staff': user.is_staff,
        })

class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        user = request.user
        for field in ['full_name', 'phone', 'email']:
            if field in request.data:
                setattr(user, field, request.data[field])
        user.save()
        return Response(UserSerializer(user).data)

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh = request.data.get('refresh')
            if refresh:
                token = RefreshToken(refresh)
                token.blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception:
            return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Admin-only endpoints ─────────────────────────────────────

class UserListView(generics.ListAPIView):
    """List all users with role=USER. Admin only."""
    serializer_class = AdminUserSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return User.objects.filter(role='USER').order_by('-date_joined')


class MerchantListView(generics.ListAPIView):
    """List all users with role=MERCHANT. Admin only."""
    serializer_class = AdminUserSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return User.objects.filter(role='MERCHANT').order_by('-date_joined')


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Admin can view, update status, or delete any user."""
    queryset = User.objects.all()
    serializer_class = AdminUserSerializer
    permission_classes = [IsAuthenticated]

    def patch(self, request, *args, **kwargs):
        user = self.get_object()
        new_status = request.data.get('status')
        new_role = request.data.get('role')

        if new_status:
            user.status = new_status
            # Sync is_active with status
            user.is_active = (new_status == 'ACTIVE')
            user.save()

        if new_role:
            user.role = new_role
            user.save()

        return Response(AdminUserSerializer(user).data)


class AdminStatsView(APIView):
    """Return platform-wide statistics for the admin dashboard overview."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from books.models import Book
        from orders.models import Order

        total_users = User.objects.filter(role='USER').count()
        total_merchants = User.objects.filter(role='MERCHANT').count()
        total_books = Book.objects.count()
        total_orders = Order.objects.count()
        pending_approvals = Book.objects.filter(approved=False).count()

        revenue_result = Order.objects.filter(status='PAID').aggregate(total=Sum('total_amount'))
        total_revenue = float(revenue_result['total'] or 0)

        return Response({
            'total_users': total_users,
            'total_merchants': total_merchants,
            'total_books': total_books,
            'total_orders': total_orders,
            'total_revenue': total_revenue,
            'pending_approvals': pending_approvals,
        })


# ─── User Address endpoints ──────────────────────────────────

class AddressListCreateView(generics.ListCreateAPIView):
    serializer_class = UserAddressSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserAddress.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class AddressDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = UserAddressSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserAddress.objects.filter(user=self.request.user)


# ─── User Preferences endpoints ──────────────────────────────

class PreferencesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        prefs, _ = UserPreferences.objects.get_or_create(user=request.user)
        return Response(UserPreferencesSerializer(prefs).data)

    def put(self, request):
        prefs, _ = UserPreferences.objects.get_or_create(user=request.user)
        serializer = UserPreferencesSerializer(prefs, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
