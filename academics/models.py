from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL

class Subject(models.Model):
    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=20, unique=True)

    def __str__(self):
        return f"{self.name} ({self.code})"

class Teacher(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='teacher_profile')
    specialty = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True)
    is_class_teacher = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    def __str__(self):
        u = self.user
        return f"{u.first_name} {u.last_name} — {u.phone}"

class SchoolClass(models.Model):
    name = models.CharField(max_length=50, unique=True)  # e.g., "7-A"
    level = models.PositiveIntegerField(null=True, blank=True)
    class_teacher = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, blank=True, related_name='classes_as_class_teacher')
    capacity = models.PositiveIntegerField(default=40)

    def __str__(self):
        return self.name

class Student(models.Model):
    GENDER = (
        ('m', 'O‘g‘il'),
        ('f', 'Qiz'),
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    dob = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER, default='m')
    clazz = models.ForeignKey(SchoolClass, on_delete=models.SET_NULL, null=True, related_name='students')
    parent_name = models.CharField(max_length=150, blank=True)
    parent_phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, default='active')

    class Meta:
        unique_together = []
        indexes = [
            models.Index(fields=['last_name', 'first_name']),
        ]

    def __str__(self):
        return f"{self.last_name} {self.first_name}"