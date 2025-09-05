from django.contrib import admin
from .models import Subject, Teacher, SchoolClass, Student

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'code')
    search_fields = ('name', 'code')

@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'specialty', 'is_class_teacher')
    search_fields = ('user__phone', 'user__first_name', 'user__last_name')
    list_filter = ('is_class_teacher', 'specialty')

@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'level', 'class_teacher', 'capacity')
    search_fields = ('name',)
    list_filter = ('level',)

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('id', 'last_name', 'first_name', 'clazz', 'status')
    search_fields = ('last_name', 'first_name', 'parent_phone')
    list_filter = ('status', 'clazz')