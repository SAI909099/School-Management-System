from rest_framework import serializers
from accounts.models import User
from .models import Subject, Teacher, SchoolClass, Student

class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ('id', 'name', 'code')

class TeacherSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())

    class Meta:
        model = Teacher
        fields = ('id', 'user', 'specialty', 'is_class_teacher', 'notes')

class SchoolClassSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchoolClass
        fields = ('id', 'name', 'level', 'class_teacher', 'capacity')

class StudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = (
            'id', 'first_name', 'last_name', 'dob', 'gender', 'clazz',
            'parent_name', 'parent_phone', 'address', 'status'
        )