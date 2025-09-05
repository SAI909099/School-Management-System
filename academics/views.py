from rest_framework import viewsets, permissions
from rest_framework.response import Response
from rest_framework.decorators import action

from accounts.models import User
from .models import Subject, Teacher, SchoolClass, Student
from .serializers import (
    SubjectSerializer, TeacherSerializer, SchoolClassSerializer, StudentSerializer
)
from .permissions import IsAdminOrRegistrarWrite

class SubjectViewSet(viewsets.ModelViewSet):
    queryset = Subject.objects.all().order_by('name')
    serializer_class = SubjectSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarWrite]

class TeacherViewSet(viewsets.ModelViewSet):
    queryset = Teacher.objects.select_related('user', 'specialty').all()
    serializer_class = TeacherSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarWrite]

class SchoolClassViewSet(viewsets.ModelViewSet):
    queryset = SchoolClass.objects.select_related('class_teacher').all().order_by('name')
    serializer_class = SchoolClassSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarWrite]

class StudentViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.select_related('clazz').all()
    serializer_class = StudentSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarWrite]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.role == 'teacher':
            try:
                teacher = user.teacher_profile
                qs = qs.filter(clazz__class_teacher=teacher)
            except Teacher.DoesNotExist:
                qs = qs.none()
        return qs

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def me_class(self, request):
        """For teachers: list my class students (if I am class teacher)."""
        user = request.user
        if user.role != 'teacher':
            return Response([])
        try:
            teacher = user.teacher_profile
        except Teacher.DoesNotExist:
            return Response([])
        students = Student.objects.filter(clazz__class_teacher=teacher)
        return Response(StudentSerializer(students, many=True).data)