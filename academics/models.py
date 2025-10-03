# academics/models.py
from django.db import models
from django.db.models import Q
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError

User = settings.AUTH_USER_MODEL


class Subject(models.Model):
    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=20, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Teacher(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='teacher_profile')
    specialty = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name='specialists')
    is_class_teacher = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    def __str__(self):
        u = self.user
        full = f"{u.first_name} {u.last_name}".strip() or (getattr(u, "phone", "") or str(u))
        return f"{full} — {getattr(u, 'phone', '')}"


class SchoolClass(models.Model):
    # e.g. "7-A"
    name = models.CharField(max_length=50, unique=True)
    level = models.PositiveIntegerField(null=True, blank=True)
    class_teacher = models.ForeignKey(
        Teacher, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='classes_as_class_teacher'
    )
    capacity = models.PositiveIntegerField(default=40)

    class Meta:
        ordering = ["name"]

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
        indexes = [
            models.Index(fields=['last_name', 'first_name']),
        ]
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.last_name} {self.first_name}".strip()


class StudentGuardian(models.Model):
    student = models.ForeignKey('Student', on_delete=models.CASCADE, related_name='guardians')
    guardian = models.ForeignKey(User, on_delete=models.CASCADE, related_name='children_links')

    class Meta:
        unique_together = (('student', 'guardian'),)

    def __str__(self):
        return f"{self.guardian} → {self.student}"


class ScheduleEntry(models.Model):
    WEEKDAYS = (
        (1, 'Dushanba'), (2, 'Seshanba'), (3, 'Chorshanba'),
        (4, 'Payshanba'), (5, 'Juma'), (6, 'Shanba'),
    )
    clazz = models.ForeignKey('SchoolClass', on_delete=models.CASCADE, related_name='schedule')
    subject = models.ForeignKey('Subject', on_delete=models.CASCADE, related_name='schedule_entries')
    teacher = models.ForeignKey('Teacher', on_delete=models.CASCADE, related_name='schedule_entries')
    weekday = models.IntegerField(choices=WEEKDAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=50, blank=True)

    class Meta:
        indexes = [models.Index(fields=['clazz', 'weekday', 'start_time'])]
        ordering = ['weekday', 'start_time']

    def __str__(self):
        return f"{self.clazz} {self.get_weekday_display()} {self.start_time}-{self.end_time} {self.subject}"

    def clean(self):
        # Overlap check for same teacher/weekday/time window
        overlaps = ScheduleEntry.objects.filter(
            teacher=self.teacher,
            weekday=self.weekday,
        ).exclude(pk=self.pk).filter(
            start_time__lt=self.end_time,
            end_time__gt=self.start_time,
        )
        if overlaps.exists():
            raise ValidationError("O‘qituvchi bu vaqtda boshqa darsga qo‘yilgan.")


class Attendance(models.Model):
    """
    Attendance row can be anchored to:
      - a specific schedule slot (preferred, solves 'same subject twice' issue)
      - or legacy subject-only (when schedule is null)

    Uniqueness is enforced:
      * (student, date, schedule) — when schedule is set
      * (student, date, subject)  — only when schedule is NULL (legacy rows)
    """
    STATUS = (
        ('present', 'Kelgan'),
        ('absent', 'Kelmagan'),
        ('late', 'Kechikkan'),
        ('excused', 'Sababli'),
    )
    student = models.ForeignKey('Student', on_delete=models.CASCADE, related_name='attendance')
    date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=10, choices=STATUS, default='present')

    clazz = models.ForeignKey('SchoolClass', on_delete=models.CASCADE, related_name='attendance')
    subject = models.ForeignKey('Subject', on_delete=models.SET_NULL, null=True, blank=True, related_name='attendance')

    # NEW: exact lesson slot
    schedule = models.ForeignKey('ScheduleEntry', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='attendance')

    teacher = models.ForeignKey('Teacher', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='attendance_marked')
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            # per-slot uniqueness
            models.UniqueConstraint(fields=['student', 'date', 'schedule'],
                                    name='uniq_att_student_date_schedule'),
            # subject-based uniqueness only when no schedule is set (legacy)
            models.UniqueConstraint(fields=['student', 'date', 'subject'],
                                    name='uniq_att_student_date_subject_when_no_schedule',
                                    condition=Q(schedule__isnull=True)),
        ]
        indexes = [
            models.Index(fields=['student', 'date']),
            models.Index(fields=['date', 'schedule']),
        ]
        ordering = ['-date', 'student_id']

    def __str__(self):
        return f"{self.date} {self.student} {self.status}"

    def clean(self):
        # Must have at least one anchor
        if not self.schedule_id and not self.subject_id:
            raise ValidationError("Attendance: 'schedule' yoki 'subject' ko‘rsatilishi shart.")

    def save(self, *args, **kwargs):
        """
        When schedule is provided, auto-fill subject/clazz/teacher if missing
        so existing queries and reports continue to work.
        """
        if self.schedule_id:
            if not self.subject_id:
                self.subject_id = self.schedule.subject_id
            if not self.clazz_id:
                self.clazz_id = self.schedule.clazz_id
            if not self.teacher_id:
                self.teacher_id = self.schedule.teacher_id
        super().save(*args, **kwargs)


class GradeScale(models.Model):
    """Mapping 2..5 → GPA points (editable by Admin)."""
    name = models.CharField(max_length=50, default='Default')
    p2 = models.DecimalField(max_digits=4, decimal_places=2, default=0.00)
    p3 = models.DecimalField(max_digits=4, decimal_places=2, default=2.50)
    p4 = models.DecimalField(max_digits=4, decimal_places=2, default=3.50)
    p5 = models.DecimalField(max_digits=4, decimal_places=2, default=5.00)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-active", "name"]

    def point_for(self, score: int):
        return {2: self.p2, 3: self.p3, 4: self.p4, 5: self.p5}.get(int(score), 0)

    def __str__(self):
        return f"{self.name} ({'active' if self.active else 'inactive'})"


class GPAConfig(models.Model):
    """Weights for daily/exam/final (sum ≈ 1.0)."""
    name = models.CharField(max_length=50, default='Default')
    weight_daily = models.DecimalField(max_digits=4, decimal_places=2, default=0.50)
    weight_exam = models.DecimalField(max_digits=4, decimal_places=2, default=0.30)
    weight_final = models.DecimalField(max_digits=4, decimal_places=2, default=0.20)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-active", "name"]

    def __str__(self):
        return f"{self.name} ({'active' if self.active else 'inactive'})"


class Grade(models.Model):
    TYPE = (
        ('daily', 'Kundalik'),
        ('exam', 'Imtihon'),
        ('final', 'Yakuniy'),
    )
    student = models.ForeignKey('Student', on_delete=models.CASCADE, related_name='grades')
    subject = models.ForeignKey('Subject', on_delete=models.CASCADE, related_name='grades')
    teacher = models.ForeignKey('Teacher', on_delete=models.SET_NULL, null=True, related_name='grades_given')
    date = models.DateField(default=timezone.now)
    term = models.CharField(max_length=20, blank=True)  # e.g., 2025-1
    type = models.CharField(max_length=10, choices=TYPE, default='exam')
    score = models.IntegerField()  # 2..5
    comment = models.CharField(max_length=255, blank=True)

    class Meta:
        indexes = [models.Index(fields=['student', 'subject', 'term'])]
        ordering = ['-date', 'student_id']

    def __str__(self):
        return f"{self.student} {self.subject} {self.type} {self.score}"
