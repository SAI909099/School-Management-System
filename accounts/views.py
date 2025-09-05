from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import PhoneTokenObtainPairSerializer, RegisterUserSerializer, UserSerializer
from .permissions import IsAdmin, IsAdminOrRegistrarWrite

class LoginView(TokenObtainPairView):
    serializer_class = PhoneTokenObtainPairSerializer

class RefreshView(TokenRefreshView):
    pass

class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        return Response(UserSerializer(request.user).data)

class RegisterUserView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarWrite]
    serializer_class = RegisterUserSerializer