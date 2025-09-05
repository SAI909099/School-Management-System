from django.urls import path
from .views import LoginView, RefreshView, MeView, RegisterUserView

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('refresh/', RefreshView.as_view(), name='refresh'),
    path('me/', MeView.as_view(), name='me'),
    path('register/', RegisterUserView.as_view(), name='register-user'),
]