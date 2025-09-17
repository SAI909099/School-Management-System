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
        user = request.user
        data = UserSerializer(user).data

        # Attach teacher profile (if exists)
        teacher = getattr(user, "teacher_profile", None)
        if teacher:
            data["teacher"] = {
                "id": teacher.id,
                "subject_id": getattr(teacher.specialty, "id", None),
                "subject_name": getattr(teacher.specialty, "name", None),
            }

        # (Optional) include basic contact fields if on your model
        data["email"] = getattr(user, "email", None)
        data["phone"] = getattr(user, "phone", None)

        return Response(data)

class RegisterUserView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarWrite]
    serializer_class = RegisterUserSerializer




# apps/users/views.py (or similar)
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        return Response({
            "id": request.user.id,
            "username": request.user.username,
            "role": getattr(request.user, "role", "user"),  # e.g. teacher/parent/admin
        })
