from rest_framework import serializers
from .models import User, UserAddress, UserPreferences
from django.db.models import Sum


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'role', 'status', 'is_superuser', 'phone', 'full_name']


class AdminUserSerializer(serializers.ModelSerializer):
    order_count = serializers.SerializerMethodField()
    total_spent = serializers.SerializerMethodField()
    date_joined = serializers.DateTimeField(format='%Y-%m-%d', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'role', 'status', 'is_active',
            'date_joined', 'order_count', 'total_spent',
        ]

    def get_order_count(self, obj):
        return obj.order_set.count()

    def get_total_spent(self, obj):
        result = obj.order_set.filter(status='PAID').aggregate(total=Sum('total_amount'))
        return float(result['total'] or 0)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'role']

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            role=validated_data.get('role', 'USER')
        )
        return user


class UserAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAddress
        fields = ['id', 'label', 'full_name', 'street', 'address_line2', 'city', 'country', 'phone', 'created_at']
        read_only_fields = ['id', 'created_at']


class UserPreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreferences
        fields = ['email_notifications', 'newsletter']