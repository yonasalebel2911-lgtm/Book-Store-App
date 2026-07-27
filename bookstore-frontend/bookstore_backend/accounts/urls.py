from django.urls import path
from .views import (
    RegisterView, LoginView, ProfileView, LogoutView,
    UserListView, MerchantListView, UserDetailView, AdminStatsView,
    AddressListCreateView, AddressDetailView, PreferencesView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('signup/', RegisterView.as_view(), name='signup'),
    path('login/', LoginView.as_view(), name='login'),
    path('me/', ProfileView.as_view(), name='profile'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('users/', UserListView.as_view(), name='user-list'),
    path('users/<int:pk>/', UserDetailView.as_view(), name='user-detail'),
    path('merchants/', MerchantListView.as_view(), name='merchant-list'),
    path('stats/', AdminStatsView.as_view(), name='admin-stats'),
    path('addresses/', AddressListCreateView.as_view(), name='address-list'),
    path('addresses/<int:pk>/', AddressDetailView.as_view(), name='address-detail'),
    path('preferences/', PreferencesView.as_view(), name='preferences'),
]