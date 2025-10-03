# academics/views.py
import traceback
from collections import defaultdict
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.db.models import Count, Q, Min
from django.db.models.functions import TruncMonth
from django.shortcuts import render
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Attendance,
    GPAConfig,
    Grade,
    GradeScale,
    ScheduleEntry,
    SchoolClass,
    Student,
    StudentGuardian,
    Subject,
    Teacher,
)
from .permissions import IsAdminOrRegistrarWrite, IsAdminOrTeacherWrite
from .serializers import (
    AttendanceSerializer,
    ClassMiniSerializer,
    GPAConfigSerializer,
    GradeScaleSerializer,
    GradeSerializer,
    ScheduleEntrySerializer,
    SchoolClassSerializer,
    StudentLiteSerializer,
    StudentSerializer,
    SubjectSerializer,
    TeacherSerializer,
)

User = get_user_model()
ALLOW_DAILY = bool(getattr(settings, "ALLOW_DAILY_GRADES", True))  # backend flag


# =========================
# Helpers (AVERAGE system)
# =========================

def _subjects_for_class(class_id: int) -> list[int]:
    """
    Distinct subject IDs taught to the class (based on schedule).
    Falls back to all Subjects if the class has no schedule yet.
    """
    if not class_id:
        return list(Subject.objects.values_list("id", flat=True))
    ids = (
        ScheduleEntry.objects.filter(clazz_id=class_id)
        .values_list("subject_id", flat=True)
        .distinct()
    )
    ids = list(ids)
    if not ids:
        ids = list(Subject.objects.values_list("id", flat=True))
    return ids


def _subject_breakdown(student_id: int, subject_id: int, term: str | None = None):
    """
    Returns (exam_avg, final_avg, subject_avg) for one student/subject.

    subject_avg = average of ALL available exam+final scores.
    (Daily is not included in the "average" badge unless you change the rule.)
    """
    qs = Grade.objects.filter(student_id=student_id, subject_id=subject_id)
    if term:
        qs = qs.filter(term=term)

    exams = list(qs.filter(type="exam").values_list("score", flat=True))
    finals = list(qs.filter(type="final").values_list("score", flat=True))

    def avg(arr):
        return round(sum(arr) / len(arr), 2) if arr else None

    exam_avg = avg(exams)
    final_avg = avg(finals)
    all_scores = exams + finals
    subject_avg = avg(all_scores)
    return exam_avg, final_avg, subject_avg


def _subject_score_for_student(student_id: int, subject_id: int, term: str | None = None):
    """
    Representative score used in overall average:
      - Latest FINAL score if available
      - else average of EXAM scores
      - else None

    (Daily is not used here by design.)
    """
    qs = Grade.objects.filter(student_id=student_id, subject_id=subject_id)
    if term:
        qs = qs.filter(term=term)

    final = qs.filter(type="final").order_by("-date", "-id").first()
    if final and final.score is not None:
        return float(final.score)

    exam_scores = list(qs.filter(type="exam").values_list("score", flat=True))
    if exam_scores:
        return float(sum(exam_scores) / len(exam_scores))

    return None


# =========================
# CRUD ViewSets
# =========================

class SubjectViewSet(viewsets.ModelViewSet):
    queryset = Subject.objects.all().order_by("name")
    serializer_class = SubjectSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarWrite]


class TeacherViewSet(viewsets.ModelViewSet):
    queryset = Teacher.objects.select_related("user", "specialty").all()
    serializer_class = TeacherSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarWrite]

    # ---- Directory (safe: only admin/registrar/operator) ----
    @action(
        detail=False,
        methods=["get"],
        url_path="directory",
        permission_classes=[permissions.IsAuthenticated],
    )
    def directory(self, request):
        role = getattr(request.user, "role", "")
        if role not in ("admin", "registrar", "operator"):
            return Response({"detail": "Forbidden"}, status=403)

        qs = (
            Teacher.objects.select_related("user")
            .all()
            .order_by("user__last_name", "user__first_name")
        )
        rows = []
        for t in qs:
            u = t.user
            rows.append(
                {
                    "id": t.id,
                    "user_id": getattr(u, "id", None),
                    "first_name": (
                        getattr(u, "first_name", "") or getattr(t, "first_name", "")
                    ).strip(),
                    "last_name": (
                        getattr(u, "last_name", "") or getattr(t, "last_name", "")
                    ).strip(),
                    "phone": getattr(u, "phone", "") or getattr(u, "username", ""),
                }
            )
        return Response(rows)

    # ---- Set password (safe: only admin/registrar/operator) ----
    @action(
        detail=True,
        methods=["post"],
        url_path="set-password",
        permission_classes=[permissions.IsAuthenticated],
    )
    def set_password(self, request, pk=None):
        role = getattr(request.user, "role", "")
        if role not in ("admin", "registrar", "operator"):
            return Response({"detail": "Forbidden"}, status=403)

        pw = (request.data.get("password") or "").strip()
        if len(pw) < 6:
            return Response(
                {"detail": "Parol uzunligi kamida 6 belgi bo‘lishi kerak"}, status=400
            )

        try:
            teacher = Teacher.objects.select_related("user").get(pk=pk)
        except Teacher.DoesNotExist:
            return Response({"detail": "Teacher not found"}, status=404)

        if not teacher.user:
            return Response(
                {"detail": "User account missing for this teacher"}, status=400
            )

        teacher.user.set_password(pw)
        teacher.user.save()
        return Response({"ok": True})


class SchoolClassViewSet(viewsets.ModelViewSet):
    """
    Full CRUD for classes + rich class actions (attendance/gradebooks/averages).
    """
    queryset = (
        SchoolClass.objects.select_related("class_teacher").all().order_by("name")
    )
    serializer_class = SchoolClassSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarWrite]

    @action(detail=True, methods=["get"])
    def students_az(self, request, pk=None):
        students = Student.objects.filter(clazz_id=pk).order_by(
            "last_name", "first_name"
        )
        return Response(StudentSerializer(students, many=True).data)

    # ---- Weekly helpers ----
    def _week_range(self, anchor: date):
        start = anchor - timedelta(days=anchor.weekday())  # Monday
        end = start + timedelta(days=5)  # Saturday
        return start, end

    # ---- Attendance grid for a class (Mon..Sat) ----
    @action(detail=True, methods=["get"])
    def attendance_grid(self, request, pk=None):
        d = request.query_params.get("week_of")
        anchor = date.fromisoformat(d) if d else date.today()
        start, end = self._week_range(anchor)

        students = list(
            Student.objects.filter(clazz_id=pk)
            .order_by("last_name", "first_name")
            .values("id", "first_name", "last_name")
        )
        att = Attendance.objects.filter(clazz_id=pk, date__range=(start, end))
        grid = defaultdict(dict)
        for a in att:
            grid[a.student_id][a.date.isoformat()] = a.status
        days = [(start + timedelta(days=i)).isoformat() for i in range(6)]
        return Response({"students": students, "days": days, "grid": grid})

    # ---- Exam gradebook ----
    @action(detail=True, methods=["get"])
    def gradebook_exams(self, request, pk=None):
        term = request.query_params.get("term", "")
        grades = Grade.objects.filter(student__clazz_id=pk, type="exam")
        if term:
            grades = grades.filter(term=term)
        data = defaultdict(list)
        for g in grades.order_by("date"):
            data[g.student_id].append(
                {"subject": g.subject_id, "date": g.date, "score": g.score}
            )
        return Response(data)

    # ---- Final gradebook ----
    @action(detail=True, methods=["get"])
    def gradebook_final(self, request, pk=None):
        term = request.query_params.get("term", "")
        grades = Grade.objects.filter(student__clazz_id=pk, type="final")
        if term:
            grades = grades.filter(term=term)
        data = defaultdict(list)
        for g in grades.order_by("date"):
            data[g.student_id].append(
                {"subject": g.subject_id, "date": g.date, "score": g.score}
            )
        return Response(data)

    # ---- Average ranking for a class ----
    @action(detail=True, methods=["get"])
    def average_ranking(self, request, pk=None):
        """
        GET /api/classes/{id}/average_ranking/?term=2025-1 (optional)
        Ranking by arithmetic average across the class's subjects.
        Subject score = latest FINAL else average of EXAMs.
        """
        term = request.query_params.get("term") or None

        students = Student.objects.filter(clazz_id=pk).order_by(
            "last_name", "first_name"
        )
        subject_ids = _subjects_for_class(pk)

        ranking = []
        for s in students:
            scores = []
            for sid in subject_ids:
                sc = _subject_score_for_student(s.id, sid, term=term)
                if sc is not None:
                    scores.append(sc)
            avg = (sum(scores) / len(scores)) if scores else 0.0
            ranking.append(
                {
                    "student_id": s.id,
                    "name": f"{s.last_name} {s.first_name}",
                    "avg": round(avg, 2),
                    "count_subjects": len(scores),
                }
            )

        ranking.sort(key=lambda x: x["avg"], reverse=True)
        for i, row in enumerate(ranking, start=1):
            row["rank"] = i

        return Response({"class_id": pk, "ranking": ranking})


class StudentViewSet(viewsets.ModelViewSet):
    """
    Full CRUD for students, scoped by teacher for GET list.
    """
    queryset = Student.objects.select_related("clazz").all()
    serializer_class = StudentSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarWrite]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "role", None) == "teacher":
            try:
                teacher = user.teacher_profile
                qs = qs.filter(clazz__class_teacher=teacher)
            except Teacher.DoesNotExist:
                qs = qs.none()
        return qs

    @action(
        detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated]
    )
    def me_class(self, request):
        """For teachers: list my class students (if I am class teacher)."""
        user = request.user
        if getattr(user, "role", None) != "teacher":
            return Response([])
        try:
            teacher = user.teacher_profile
        except Teacher.DoesNotExist:
            return Response([])
        students = Student.objects.filter(clazz__class_teacher=teacher)
        return Response(StudentSerializer(students, many=True).data)


class ScheduleEntryViewSet(viewsets.ModelViewSet):
    queryset = ScheduleEntry.objects.select_related("clazz", "teacher", "subject").all()
    serializer_class = ScheduleEntrySerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarWrite]

    @action(detail=False, methods=["get"], url_path="class/(?P<class_id>[^/.]+)")
    def by_class(self, request, class_id=None):
        qs = self.queryset.filter(clazz_id=class_id).order_by("weekday", "start_time")
        return Response(self.serializer_class(qs, many=True).data)

    @action(detail=False, methods=["get"], url_path="teacher/me")
    def my_schedule(self, request):
        user = request.user
        if getattr(user, "role", None) != "teacher":
            return Response([])
        try:
            t = user.teacher_profile
        except Teacher.DoesNotExist:
            return Response([])
        qs = self.queryset.filter(teacher=t)
        return Response(self.serializer_class(qs, many=True).data)

    @action(detail=False, methods=["get"], url_path="teacher/(?P<teacher_id>[^/.]+)")
    def by_teacher_id(self, request, teacher_id=None):
        qs = self.queryset.filter(teacher_id=teacher_id).order_by(
            "weekday", "start_time"
        )
        return Response(self.serializer_class(qs, many=True).data)

    def get_queryset(self):
        qs = super().get_queryset()
        teacher_id = self.request.query_params.get("teacher")
        class_id = self.request.query_params.get("clazz") or self.request.query_params.get(
            "class"
        )
        if teacher_id:
            qs = qs.filter(teacher_id=teacher_id)
        if class_id:
            qs = qs.filter(clazz_id=class_id)
        return qs.order_by("weekday", "start_time")


# =========================
# Attendance (per-lesson safe)
# =========================

class AttendanceViewSet(viewsets.ModelViewSet):
    """
    CRUD + utilities for attendance.

    Backward compatible:
      - If `schedule` is provided, it uniquely identifies the lesson on that day.
      - Else fall back to `subject` (legacy).
    """
    queryset = (
        Attendance.objects.select_related(
            "student",
            "clazz",
            "subject",
            "teacher",
            "schedule",
            "schedule__subject",
            "schedule__clazz",
        ).all()
    )
    serializer_class = AttendanceSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrTeacherWrite]

    # ---- base scoping for list/retrieve ----
    def get_queryset(self):
        qs = super().get_queryset().distinct()
        u = self.request.user
        role = getattr(u, "role", None)

        if role == "teacher":
            try:
                t = u.teacher_profile
                qs = qs.filter(
                    Q(clazz__class_teacher=t)
                    | Q(teacher=t)
                    | Q(student__clazz__schedule__teacher=t)
                )
            except Teacher.DoesNotExist:
                return Attendance.objects.none()

        elif role == "parent":
            child_ids = StudentGuardian.objects.filter(guardian=u).values_list(
                "student_id", flat=True
            )
            qs = qs.filter(student_id__in=child_ids)

        return qs

    # ---- bulk mark: used by teacher page ----
    @action(detail=False, methods=["post"], url_path="bulk-mark")
    def bulk_mark(self, request):
        """
        Payload:
        {
          "class": <id>, "date": "YYYY-MM-DD",
          "schedule": <id or null>,   # NEW (preferred)
          "subject":  <id or null>,   # legacy fallback
          "entries": [{"student":id, "status":"present|absent|late|excused", "note":""}]
        }
        """
        u = request.user
        if getattr(u, "role", None) not in ("admin", "teacher", "registrar", "operator"):
            return Response({"detail": "Forbidden"}, status=403)

        clazz = request.data.get("class")
        dt = request.data.get("date")
        schedule_id = request.data.get("schedule")
        subject = request.data.get("subject")
        entries = request.data.get("entries", [])

        if not clazz or not dt or not isinstance(entries, list):
            return Response({"detail": "class, date and entries are required"}, status=400)
        try:
            date.fromisoformat(dt)
        except Exception:
            return Response({"detail": "invalid date (YYYY-MM-DD)"}, status=400)

        # Validate/resolve schedule if provided
        sch = None
        if schedule_id:
            try:
                sch = ScheduleEntry.objects.select_related("clazz", "subject").get(
                    id=schedule_id
                )
            except ScheduleEntry.DoesNotExist:
                return Response({"detail": "schedule not found"}, status=404)
            if int(sch.clazz_id) != int(clazz):
                return Response(
                    {"detail": "schedule does not belong to provided class"}, status=400
                )

        try:
            t = u.teacher_profile if getattr(u, "role", None) == "teacher" else None
        except Teacher.DoesNotExist:
            t = None

        ids = []
        for e in entries:
            sid = e.get("student")
            st = e.get("status")
            if not sid or st not in ("present", "absent", "late", "excused"):
                continue

            # Unique key prefers schedule; else legacy subject
            key = {"student_id": sid, "date": dt}
            if sch is not None:
                key["schedule_id"] = sch.id
            else:
                key["subject_id"] = subject

            defaults = {
                "status": st,
                "note": e.get("note", ""),
                "clazz_id": clazz,
                "teacher": t,
            }
            if sch is not None:
                defaults.setdefault("subject_id", getattr(sch, "subject_id", None))

            obj, _ = Attendance.objects.update_or_create(**key, defaults=defaults)
            ids.append(obj.id)

        return Response({"ok": True, "ids": ids})

    # ---- simple mark: used by operator page (boolean present) ----
    @action(detail=False, methods=["post"], url_path="mark")
    def mark(self, request):
        """
        Payload:
        {
          "class_id": <id>,
          "date": "YYYY-MM-DD",
          "schedule": <id or null>,   # NEW (preferred)
          "subject":  <id or null>,   # legacy fallback
          "items": [{"student": id, "present": true|false}]
        }
        """
        u = request.user
        if getattr(u, "role", None) not in ("admin", "registrar", "operator", "teacher"):
            return Response({"detail": "Forbidden"}, status=403)

        clazz = request.data.get("class_id")
        dt = request.data.get("date")
        schedule_id = request.data.get("schedule")
        subject = request.data.get("subject")
        items = request.data.get("items", [])

        if not clazz or not dt or not isinstance(items, list):
            return Response(
                {"detail": "class_id, date and items are required"}, status=400
            )
        try:
            date.fromisoformat(dt)
        except Exception:
            return Response({"detail": "invalid date (YYYY-MM-DD)"}, status=400)

        sch = None
        if schedule_id:
            try:
                sch = ScheduleEntry.objects.select_related("clazz", "subject").get(
                    id=schedule_id
                )
            except ScheduleEntry.DoesNotExist:
                return Response({"detail": "schedule not found"}, status=404)
            if int(sch.clazz_id) != int(clazz):
                return Response(
                    {"detail": "schedule does not belong to provided class"}, status=400
                )

        try:
            t = u.teacher_profile if getattr(u, "role", None) == "teacher" else None
        except Teacher.DoesNotExist:
            t = None

        ids = []
        for it in items:
            sid = it.get("student")
            if not sid:
                continue
            status_val = "present" if bool(it.get("present")) else "absent"

            key = {"student_id": sid, "date": dt}
            if sch is not None:
                key["schedule_id"] = sch.id
            else:
                key["subject_id"] = subject

            defaults = {"status": status_val, "note": "", "clazz_id": clazz, "teacher": t}
            if sch is not None:
                defaults.setdefault("subject_id", getattr(sch, "subject_id", None))

            obj, _ = Attendance.objects.update_or_create(**key, defaults=defaults)
            ids.append(obj.id)

        return Response({"ok": True, "ids": ids})

    # ---- read back saved marks for a class/day (+ optional schedule/subject) ----
    @action(detail=False, methods=["get"], url_path="by-class-day")
    def by_class_day(self, request):
        """
        GET /api/attendance/by-class-day/?class=<id>&date=YYYY-MM-DD&schedule=<id?>&subject=<id?>
        Returns: [{"student_id":..., "status":"present|absent|late|excused", "note": "..."}]
        """
        clazz = request.query_params.get("class")
        dt = request.query_params.get("date")
        schedule_id = request.query_params.get("schedule")
        subject = request.query_params.get("subject")

        if not clazz or not dt:
            return Response({"detail": "class and date are required"}, status=400)
        try:
            date.fromisoformat(dt)
        except Exception:
            return Response({"detail": "invalid date (YYYY-MM-DD)"}, status=400)

        qs = self.get_queryset().filter(clazz_id=clazz, date=dt)
        if schedule_id:
            qs = qs.filter(schedule_id=schedule_id)
        elif subject:
            qs = qs.filter(subject_id=subject)

        data = qs.values("student_id", "status", "note")
        return Response(list(data))

    # ---- "Kelmaganlar" list (1 row per student for the day) ----
    @action(detail=False, methods=["get"], url_path="absent")
    def absent(self, request):
        date_str = request.query_params.get("date")
        if not date_str:
            return Response({"detail": "date is required (YYYY-MM-DD)"}, status=400)
        try:
            date.fromisoformat(date_str)
        except Exception:
            return Response({"detail": "invalid date (YYYY-MM-DD)"}, status=400)

        class_id = request.query_params.get("class")
        base_qs = self.get_queryset().filter(date=date_str, status="absent")
        if class_id:
            base_qs = base_qs.filter(clazz_id=class_id)

        ids_qs = (
            base_qs.values("student_id")
            .annotate(first_id=Min("id"))
            .values_list("first_id", flat=True)
        )
        qs = Attendance.objects.filter(id__in=ids_qs).select_related("student", "clazz")

        rows = []
        for a in qs:
            s = a.student
            full_name = (
                f"{getattr(s, 'last_name', '')} {getattr(s, 'first_name', '')}".strip()
                or getattr(s, "full_name", "")
                or f"#{s.id}"
            )
            class_name = (
                a.clazz.name
                if a.clazz
                else (getattr(s.clazz, "name", "") if getattr(s, "clazz", None) else "")
            )
            rows.append(
                {
                    "student_id": s.id,
                    "full_name": full_name,
                    "class_name": class_name,
                    "parent_phone": getattr(s, "parent_phone", "") or "",
                }
            )
        return Response(rows)


# =========================
# Grades (daily | exam | final)
# =========================

class GradeViewSet(viewsets.ModelViewSet):
    """
    Secure Grade API:
      - Role-scoped reads (teacher/parent).
      - Safe bulk_set for daily|exam|final (atomic + strict validation).
      - Read filters with guardrails.
      - Weekly daily grid helper (read-only).
      - Parent-friendly daily-by-student view.
    """
    queryset = Grade.objects.select_related("student", "subject", "teacher").all()
    serializer_class = GradeSerializer
    permission_classes = [permissions.IsAuthenticated]  # write guarded per-action

    # --------- Base scoping for reads ---------
    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        role = getattr(u, "role", None)

        if role == "teacher":
            try:
                t = u.teacher_profile
            except Teacher.DoesNotExist:
                return Grade.objects.none()
            # Teacher can see: their class students OR grades they gave
            qs = qs.filter(Q(student__clazz__class_teacher=t) | Q(teacher=t))

        elif role == "parent":
            # Parent sees only their children
            child_ids = StudentGuardian.objects.filter(guardian=u).values_list(
                "student_id", flat=True
            )
            qs = qs.filter(student_id__in=child_ids)

        # Admin/registrar/operator/accountant can see all
        return qs

    # --------- WRITE: Bulk set daily|exam|final (atomic) ---------
    @action(detail=False, methods=["post"], url_path="bulk-set")
    def bulk_set(self, request):
        """
        Payload:
        {
          "class": <id>, "date":"YYYY-MM-DD", "subject": <id>,
          "type":"daily|exam|final", "term":"2025-1",
          "entries":[{"student":<id>, "score":2..5, "comment":""}, ...]   # max 300 per call
        }
        """
        u = request.user
        role = getattr(u, "role", None)
        if role not in ("admin", "teacher"):
            return Response({"detail": "Forbidden"}, status=403)

        data = request.data or {}
        clazz = data.get("class")
        dt_str = (data.get("date") or "").strip()
        subject_id = data.get("subject")
        gtype = (data.get("type") or "").strip()
        term = (data.get("term") or "").strip()
        entries = data.get("entries") or []

        # Basic checks
        if not clazz or not dt_str or not subject_id:
            return Response({"detail": "class, date and subject are required"}, status=400)
        try:
            dt = date.fromisoformat(dt_str)
        except Exception:
            return Response({"detail": "invalid date (use YYYY-MM-DD)"}, status=400)

        allowed = ("exam", "final") + (("daily",) if ALLOW_DAILY else ())
        if gtype not in allowed:
            return Response(
                {
                    "detail": (
                        'type must be "exam" or "final"'
                        if not ALLOW_DAILY
                        else 'type must be "daily", "exam" or "final"'
                    )
                },
                status=400,
            )

        if not isinstance(entries, list) or not entries:
            return Response({"detail": "entries must be a non-empty list"}, status=400)
        if len(entries) > 300:
            return Response({"detail": "too many entries (max 300 per request)"}, status=400)

        if term and len(term) > 20:
            return Response({"detail": "term is too long (max 20 characters)"}, status=400)

        # Validate subject exists
        if not Subject.objects.filter(id=subject_id).exists():
            return Response({"detail": "subject not found"}, status=404)

        # Validate class exists & preload students
        class_student_ids = set(
            Student.objects.filter(clazz_id=clazz).values_list("id", flat=True)
        )
        if not class_student_ids:
            return Response({"detail": "class not found or has no students"}, status=404)

        # If teacher, ensure they are allowed to write this class/subject
        teacher_obj = None
        if role == "teacher":
            try:
                teacher_obj = u.teacher_profile
            except Teacher.DoesNotExist:
                teacher_obj = None
            allowed_scope = (
                SchoolClass.objects.filter(id=clazz, class_teacher=teacher_obj).exists()
                or ScheduleEntry.objects.filter(
                    clazz_id=clazz, subject_id=subject_id, teacher=teacher_obj
                ).exists()
            )
            if not allowed_scope:
                return Response(
                    {"detail": "Forbidden: not assigned to this class/subject"}, status=403
                )

        # Validate all entries first (no partial writes)
        seen = set()
        cleaned = []
        for i, e in enumerate(entries, start=1):
            sid = e.get("student")
            score = e.get("score")
            comment = (e.get("comment") or "").strip()

            if sid is None:
                return Response({"detail": f"entries[{i}].student is required"}, status=400)
            if sid not in class_student_ids:
                return Response(
                    {"detail": f"student {sid} does not belong to class {clazz}"},
                    status=400,
                )

            # avoid duplicate student rows in one payload
            if sid in seen:
                return Response(
                    {"detail": f"duplicate entry for student {sid} in payload"}, status=400
                )
            seen.add(sid)

            # score must be int in 2..5
            try:
                score_int = int(score)
            except Exception:
                return Response(
                    {"detail": f"entries[{i}].score must be integer 2..5"}, status=400
                )
            if score_int < 2 or score_int > 5:
                return Response(
                    {"detail": f"entries[{i}].score must be between 2 and 5"}, status=400
                )
            if len(comment) > 255:
                return Response(
                    {"detail": f"entries[{i}].comment too long (max 255)"}, status=400
                )

            cleaned.append((sid, score_int, comment))

        # Atomic upsert
        ids = []
        with transaction.atomic():
            for sid, score_int, comment in cleaned:
                obj, _ = Grade.objects.update_or_create(
                    student_id=sid,
                    subject_id=subject_id,
                    date=dt,
                    type=gtype,  # daily | exam | final
                    defaults={
                        "score": score_int,
                        "comment": comment,
                        "teacher": teacher_obj if role == "teacher" else None,
                        "term": term,
                    },
                )
                ids.append(obj.id)

        return Response({"ok": True, "ids": ids}, status=200)

    # --------- READ: Filtered list for a class ---------
    @action(detail=False, methods=["get"], url_path="by-class")
    def by_class(self, request):
        """
        GET /api/grades/by-class/?class=<id>&subject=<id>&type=daily|exam|final&date=YYYY-MM-DD&term=2025-1
        Returns: [{"student_id":..., "score":..., "comment":"..."}, ...]
        """
        qs = self.get_queryset()

        clazz = request.query_params.get("class")
        subject = request.query_params.get("subject")
        gtype = request.query_params.get("type")
        dt = request.query_params.get("date")
        term = request.query_params.get("term", "")

        if clazz:
            qs = qs.filter(student__clazz_id=clazz)
        if subject:
            qs = qs.filter(subject_id=subject)
        if gtype:
            allowed = ("exam", "final") + (("daily",) if ALLOW_DAILY else ())
            if gtype not in allowed:
                return Response(
                    {
                        "detail": (
                            'type must be "exam" or "final"'
                            if not ALLOW_DAILY
                            else 'type must be "daily", "exam" or "final"'
                        )
                    },
                    status=400,
                )
            qs = qs.filter(type=gtype)
        if dt:
            try:
                date.fromisoformat(dt)
            except Exception:
                return Response({"detail": "invalid date (use YYYY-MM-DD)"}, status=400)
            qs = qs.filter(date=dt)
        if term:
            qs = qs.filter(term=term)

        data = qs.values("student_id", "score", "comment")
        return Response(list(data), status=200)

    # --------- READ: Weekly grid for DAILY grades (class view) ---------
    @action(detail=False, methods=["get"], url_path="daily-grid")
    def daily_grid(self, request):
        """
        GET /api/grades/daily-grid/?class=<id>&subject=<id>&week_of=YYYY-MM-DD
        Returns weekly Mon..Sat grid for 'daily' type:
        {
          "days": ["YYYY-MM-DD", ... 6 days],
          "students": [{"id":..,"first_name":..,"last_name":..}, ...],
          "grid": { "<student_id>": { "<YYYY-MM-DD>": {"score": 4, "comment": ""} } }
        }
        """
        clazz = request.query_params.get("class")
        subject = request.query_params.get("subject")
        d = request.query_params.get("week_of")

        if not clazz or not subject:
            return Response({"detail": "class and subject are required"}, status=400)

        try:
            anchor = date.fromisoformat(d) if d else date.today()
        except Exception:
            return Response({"detail": "invalid week_of (use YYYY-MM-DD)"}, status=400)

        start = anchor - timedelta(days=anchor.weekday())  # Monday
        end = start + timedelta(days=5)                    # Mon..Sat
        days = [(start + timedelta(days=i)).isoformat() for i in range(6)]

        students = list(
            Student.objects
            .filter(clazz_id=clazz)
            .order_by("last_name", "first_name")
            .values("id", "first_name", "last_name")
        )

        qs = (
            self.get_queryset()
            .filter(
                student__clazz_id=clazz,
                subject_id=subject,
                type="daily",
                date__range=(start, end),
            )
            .order_by("date")
        )

        grid = defaultdict(dict)
        for g in qs:
            grid[str(g.student_id)][g.date.isoformat()] = {'score': g.score, 'comment': g.comment}

        return Response({"days": days, "students": students, "grid": grid}, status=200)

    # --------- READ: Parent/Teacher-friendly daily-by-student (Mon..Sat) ---------
    @action(detail=False, methods=["get"], url_path="daily-by-student")
    def daily_by_student(self, request):
        """
        GET /api/grades/daily-by-student/?student=<id>&week_of=YYYY-MM-DD (optional)
        Returns:
        {
          "student": {"id":..,"first_name":..,"last_name":..,"class_id":..,"class_name":"..."},
          "days": ["YYYY-MM-DD", ... 6 days],
          "subjects": [{"id":..,"name":"..."}, ...],
          "grid": { "<subject_id>": { "<YYYY-MM-DD>": {"score": 4, "comment": ""} } }
        }
        """
        student_id = request.query_params.get("student")
        if not student_id:
            return Response({"detail": "student is required"}, status=400)

        # resolve student
        try:
            s = Student.objects.select_related("clazz").get(id=student_id)
        except Student.DoesNotExist:
            return Response({"detail": "Student not found"}, status=404)

        # --- permissions ---
        u = request.user
        role = getattr(u, "role", None)
        allowed = False
        if role in ("admin", "registrar", "operator", "accountant"):
            allowed = True
        elif role == "parent":
            allowed = StudentGuardian.objects.filter(guardian=u, student=s).exists()
        elif role == "teacher":
            try:
                t = u.teacher_profile
            except Teacher.DoesNotExist:
                t = None
            if t:
                allowed = (
                    SchoolClass.objects.filter(id=s.clazz_id, class_teacher=t).exists()
                    or ScheduleEntry.objects.filter(clazz_id=s.clazz_id, teacher=t).exists()
                )
        if not allowed:
            return Response({"detail": "Forbidden"}, status=403)

        # week range (Mon..Sat)
        d_str = request.query_params.get("week_of")
        try:
            anchor = date.fromisoformat(d_str) if d_str else date.today()
        except Exception:
            return Response({"detail": "invalid week_of (use YYYY-MM-DD)"}, status=400)
        start = anchor - timedelta(days=anchor.weekday())
        end = start + timedelta(days=5)
        days = [(start + timedelta(days=i)).isoformat() for i in range(6)]

        # subjects for this student's class
        subj_ids = (
            _subjects_for_class(s.clazz_id)
            if s.clazz_id
            else list(Subject.objects.values_list("id", flat=True))
        )
        subjects = list(
            Subject.objects.filter(id__in=subj_ids).order_by("name").values("id", "name")
        )
        subj_id_set = {x["id"] for x in subjects}

        # fetch DAILY grades for the week
        qs = (
            Grade.objects.filter(
                student_id=s.id,
                type="daily",
                date__range=(start, end),
                subject_id__in=subj_id_set,
            )
            .order_by("subject_id", "date", "id")
        )

        grid = defaultdict(dict)
        for g in qs:
            grid[str(g.subject_id)][g.date.isoformat()] = {
                "score": g.score,
                "comment": g.comment or "",
            }

        payload = {
            "student": {
                "id": s.id,
                "first_name": s.first_name,
                "last_name": s.last_name,
                "class_id": s.clazz_id,
                "class_name": (s.clazz.name if s.clazz else ""),
            },
            "days": days,
            "subjects": subjects,
            "grid": grid,
        }
        return Response(payload, status=200)


# =========================
# Dashboards / Parent
# =========================

class TeacherDashViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="classes/me")
    def my_classes(self, request):
        u = request.user
        if getattr(u, "role", None) != "teacher":
            return Response([])
        try:
            t = u.teacher_profile
        except Teacher.DoesNotExist:
            return Response([])
        classes = (
            SchoolClass.objects.filter(Q(class_teacher=t) | Q(schedule__teacher=t))
            .distinct()
            .order_by("name")
        )
        return Response(SchoolClassSerializer(classes, many=True).data)


class ParentViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="children")
    def children(self, request):
        u = request.user
        if getattr(u, "role", None) != "parent":
            return Response([])
        child_ids = StudentGuardian.objects.filter(guardian=u).values_list(
            "student_id", flat=True
        )
        kids = Student.objects.filter(id__in=child_ids).order_by(
            "last_name", "first_name"
        )
        return Response(StudentSerializer(kids, many=True).data)

    @action(detail=False, methods=["get"], url_path="child/(?P<student_id>[^/.]+)/overview")
    def child_overview(self, request, student_id=None):
        u = request.user
        if getattr(u, "role", None) != "parent":
            return Response({"detail": "Forbidden"}, status=403)
        if not StudentGuardian.objects.filter(
            guardian=u, student_id=student_id
        ).exists():
            return Response({"detail": "Forbidden"}, status=403)

        s = Student.objects.select_related("clazz").get(id=student_id)
        timetable = ScheduleEntry.objects.filter(clazz=s.clazz).order_by(
            "weekday", "start_time"
        )

        # latest week Mon..Sat
        today = date.today()
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=5)
        latest_att = Attendance.objects.filter(student=s, date__range=(start, end))

        # ---- Average-based summary (exam+final) ----
        subject_ids = (
            _subjects_for_class(s.clazz_id)
            if s.clazz_id
            else list(Subject.objects.values_list("id", flat=True))
        )
        names = {sub.id: sub.name for sub in Subject.objects.filter(id__in=subject_ids)}

        grades_summary = {}
        subject_scores = {}
        scores_for_overall = []

        for sid in subject_ids:
            exam_avg, final_avg, subject_avg = _subject_breakdown(s.id, sid, term=None)
            # show only if there is at least one score
            if exam_avg is not None or final_avg is not None:
                nm = names.get(sid, f"Subject #{sid}")
                grades_summary[nm] = {
                    "exam_avg": exam_avg,
                    "final_avg": final_avg,
                    "subject_avg": subject_avg,
                    "gpa_subject": subject_avg,
                }
            # representative score for overall
            rep = _subject_score_for_student(s.id, sid, term=None)
            if rep is not None:
                subject_scores[nm] = round(rep, 2)
                scores_for_overall.append(rep)

        avg_overall = (
            round(sum(scores_for_overall) / len(scores_for_overall), 2)
            if scores_for_overall
            else 0.0
        )

        # Rank inside the class using the same averaging rule
        ranking = (
            SchoolClassViewSet().average_ranking(request, pk=s.clazz_id).data["ranking"]
            if s.clazz_id
            else []
        )
        my_row = next((r for r in ranking if r["student_id"] == s.id), None)
        my_rank = my_row["rank"] if my_row else None
        class_size = s.clazz.students.count() if s.clazz else 0

        payload = {
            "student": StudentSerializer(s).data,
            "class_name": s.clazz.name if s.clazz else "",
            "timetable": ScheduleEntrySerializer(timetable, many=True).data,
            "latest_week_attendance": AttendanceSerializer(latest_att, many=True).data,
            "subject_scores": subject_scores,   # {"Matematika": 4.25, ...}
            "avg_overall": avg_overall,         # e.g., 4.37
            "grades_summary": grades_summary,   # used by current JS to build the table
            "gpa_overall": avg_overall,         # keep old key so the badge shows a number
            "class_rank": my_rank,
            "class_size": class_size,
        }
        return Response(payload)


class GradeScaleViewSet(viewsets.ModelViewSet):
    """
    Retained for compatibility with existing routes; not used by average logic.
    """
    queryset = GradeScale.objects.all()
    serializer_class = GradeScaleSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarWrite]


class GPAConfigViewSet(viewsets.ModelViewSet):
    """
    Retained for compatibility with existing routes; not used by average logic.
    """
    queryset = GPAConfig.objects.all()
    serializer_class = GPAConfigSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarWrite]


# =========================
# READ-ONLY "Directory" APIs
# =========================

class ClassDirectoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Lightweight classes list with student counts (safe for directory page).
    """
    queryset = (
        SchoolClass.objects.all().annotate(students_count=Count("students")).order_by("name")
    )
    serializer_class = ClassMiniSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=["get"])
    def students(self, request, pk=None):
        qs = Student.objects.filter(clazz_id=pk).select_related("clazz")
        return Response(StudentLiteSerializer(qs, many=True).data)


class StudentDirectoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Global student search across the school.
    """
    queryset = Student.objects.select_related("clazz").all()
    serializer_class = StudentLiteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(clazz__name__icontains=q)
                | Q(parent_name__icontains=q)
                | Q(parent_phone__icontains=q)
            )
        return qs.order_by("last_name", "first_name")


# =========================
# OPERATOR one-shot enroll endpoint
# =========================

def _clean_phone(p: str) -> str:
    """Normalize to +998… (digits only) with leading +."""
    if not p:
        return ""
    digits = "".join(ch for ch in p if ch.isdigit() or ch == "+")
    digits = "".join(ch for ch in digits if ch.isdigit())
    if not digits:
        return ""
    if digits.startswith("998"):
        return "+" + digits
    return "+" + digits


class OperatorEnrollView(APIView):
    """
    POST /api/operator/enroll/
    {
      "first_name": "Ali", "last_name": "Karimov",
      "gender": "m|f",             (optional)
      "dob": "YYYY-MM-DD",         (optional)
      "class_id": 12,              (required)
      "parent_name": "Karim aka",  (optional)
      "phone1": "+998901112233",   (required) -> parent login (User.phone)
      "phone2": "+998907778899"    (optional)
    }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        role = getattr(request.user, "role", "")
        if role not in ("admin", "registrar", "operator"):
            return Response({"detail": "Forbidden"}, status=403)

        d = request.data
        first_name = (d.get("first_name") or "").strip()
        last_name = (d.get("last_name") or "").strip()
        class_id = d.get("class_id")
        parent_name = (d.get("parent_name") or "").strip()
        phone1 = _clean_phone(d.get("phone1") or "")
        phone2 = _clean_phone(d.get("phone2") or "")
        dob = d.get("dob") or None
        gender = d.get("gender") or "m"

        if not first_name or not last_name or not class_id or not phone1:
            return Response(
                {"detail": "first_name, last_name, class_id, phone1 are required"},
                status=400,
            )

        try:
            clazz = SchoolClass.objects.get(id=class_id)
        except SchoolClass.DoesNotExist:
            return Response({"detail": "Class not found"}, status=404)

        temp_password = None
        parent_user, created = User.objects.get_or_create(
            phone=phone1,
            defaults={
                "first_name": parent_name or "Ota-ona",
                "last_name": "",
            },
        )

        if getattr(parent_user, "role", "") != "parent":
            parent_user.role = "parent"
        if created:
            import secrets
            temp_password = secrets.token_urlsafe(6)
            parent_user.set_password(temp_password)
        parent_user.save()

        s = Student.objects.create(
            first_name=first_name,
            last_name=last_name,
            dob=dob,
            gender=gender,
            clazz=clazz,
            parent_name=parent_name,
            parent_phone=phone1,
            address="",
            status="active",
        )

        StudentGuardian.objects.get_or_create(student=s, guardian=parent_user)

        return Response(
            {
                "student_id": s.id,
                "class_name": clazz.name,
                "parent_username": phone1,
                "temp_password": temp_password,
            },
            status=201,
        )


# =========================
# School statistics API (for analytics page)
# =========================

class SchoolStatsView(APIView):
    """
    GET /api/stats/school/
    Returns:
    {
      "totals": {"students": int, "classes": int, "teachers": int, "active_students": int},
      "classes": [{"id": int, "name": str, "students_count": int}],
      "registrations": {
        "year": <int>,
        "available": true|false,
        "monthly": [{"month": "YYYY-MM", "count": int}],
        "total": int
      }
    }
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        role = getattr(request.user, "role", "")
        if role not in ("admin", "registrar", "operator", "teacher"):
            return Response({"detail": "Forbidden"}, status=403)

        # Totals
        field_names = {f.name for f in Student._meta.get_fields()}
        has_status = "status" in field_names
        students_q = Student.objects.all()
        active_q = Student.objects.filter(status="active") if has_status else students_q

        totals = {
            "students": students_q.count(),
            "active_students": active_q.count(),
            "classes": SchoolClass.objects.count(),
            "teachers": Teacher.objects.count(),
        }

        # Classes with student counts
        classes = (
            SchoolClass.objects
            .annotate(students_count=Count("students"))
            .order_by("name")
            .values("id", "name", "students_count")
        )

        # Registrations this year — best-effort auto date field
        year = date.today().year
        date_candidates = [
            "enrolled_at", "enrolled_date", "admission_date",
            "registered_at", "created_at", "created", "date_joined",
        ]
        date_fields = {
            f.name for f in Student._meta.get_fields()
            if isinstance(f, (models.DateField, models.DateTimeField))
        }
        date_field = next((d for d in date_candidates if d in date_fields), None)

        registrations = {"year": year, "available": bool(date_field), "monthly": [], "total": 0}
        if date_field:
            qs = (
                Student.objects
                .filter(**{f"{date_field}__year": year})
                .annotate(m=TruncMonth(date_field))
                .values("m")
                .annotate(n=Count("id"))
                .order_by("m")
            )
            monthly = [
                {"month": (row["m"].strftime("%Y-%m") if row["m"] else None), "count": row["n"]}
                for row in qs
            ]
            registrations["monthly"] = monthly
            registrations["total"] = sum(x["count"] for x in monthly)

        return Response({
            "totals": totals,
            "classes": list(classes),
            "registrations": registrations,
        })


# =========================
# Staff directory & password management (non-parents)
# =========================

class StaffDirectoryView(APIView):
    """
    GET /api/staff/directory/
    Returns a flat list of all non-parent users (teachers + other staff).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        role = getattr(request.user, "role", "")
        if role not in ("admin", "registrar", "operator"):
            return Response({"detail": "Forbidden"}, status=403)

        users = User.objects.exclude(role="parent").order_by("last_name", "first_name")

        # Map teacher profile by user_id to enrich specialty
        teacher_by_user = {
            t.user_id: t
            for t in Teacher.objects.select_related("user", "specialty").filter(
                user_id__in=[u.id for u in users]
            )
        }

        rows = []
        for u in users:
            t = teacher_by_user.get(u.id)
            specialty_name = ""
            if t and getattr(t, "specialty", None):
                specialty_name = getattr(t.specialty, "name", "") or getattr(
                    t.specialty, "title", ""
                )

            rows.append(
                {
                    "user_id": u.id,
                    "role": getattr(u, "role", "") or "",
                    "first_name": getattr(u, "first_name", "") or "",
                    "last_name": getattr(u, "last_name", "") or "",
                    "phone": getattr(u, "phone", "") or getattr(u, "username", ""),
                    "teacher_id": getattr(t, "id", None),
                    "specialty": specialty_name,
                }
            )
        return Response(rows)


class StaffSetPasswordView(APIView):
    """
    POST /api/staff/set-password/
    { "user_id": <int>, "password": "<new_password>" }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        role = getattr(request.user, "role", "")
        if role not in ("admin", "registrar", "operator"):
            return Response({"detail": "Forbidden"}, status=403)

        user_id = request.data.get("user_id")
        password = (request.data.get("password") or "").strip()

        if not user_id or not password:
            return Response({"detail": "user_id and password are required"}, status=400)
        if len(password) < 6:
            return Response(
                {"detail": "Parol uzunligi kamida 6 belgi bo‘lishi kerak"}, status=400
            )

        try:
            u = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"detail": "User not found"}, status=404)

        # Do not allow changing parent passwords via this endpoint
        if getattr(u, "role", "") == "parent":
            return Response({"detail": "Forbidden for parents"}, status=403)

        u.set_password(password)
        u.save()
        return Response({"ok": True})


# =========================
# Parents directory (no email field in payload)
# =========================

class ParentDirectoryViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        try:
            role = getattr(request.user, "role", "")
            if role not in ("admin", "registrar", "operator"):
                return Response([], status=200)

            parents = (
                User.objects.filter(role="parent")
                .only("id", "first_name", "last_name", "phone")
                .order_by("last_name", "first_name")
            )
            pids = [p.id for p in parents]

            # Gather children via forward FKs
            links = (
                StudentGuardian.objects
                .select_related("student__clazz")
                .filter(guardian_id__in=pids)
                .order_by("student__last_name", "student__first_name")
            )

            kid_map = {pid: [] for pid in pids}
            for link in links:
                s = link.student
                if not s:
                    continue
                kid_map.setdefault(link.guardian_id, []).append({
                    "id": s.id,
                    "first_name": s.first_name,
                    "last_name": s.last_name,
                    "class": (s.clazz.name if getattr(s, "clazz", None) else None),
                })

            rows = []
            for u in parents:
                rows.append({
                    "id": u.id,
                    "first_name": u.first_name or "",
                    "last_name":  u.last_name  or "",
                    "phone": getattr(u, "phone", "") or "",
                    "children": kid_map.get(u.id, []),
                })

            return Response(rows)

        except Exception as e:
            traceback.print_exc()
            return Response({"error": str(e)}, status=500)

    @action(detail=True, methods=["post"], url_path="set-password")
    def set_password(self, request, pk=None):
        try:
            role = getattr(request.user, "role", "")
            if role not in ("admin", "registrar", "operator"):
                return Response({"detail": "Forbidden"}, status=403)

            password = (request.data.get("password") or "").strip()
            if len(password) < 6:
                return Response({"detail": "Parol uzunligi kamida 6 belgi bo‘lishi kerak"}, status=400)

            parent = User.objects.get(pk=pk, role="parent")
            parent.set_password(password)
            parent.save(update_fields=["password"])
            return Response({"status": "password_changed"})
        except Exception as e:
            traceback.print_exc()
            return Response({"error": str(e)}, status=500)


# =========================
# Staff delete
# =========================

class StaffDeleteView(APIView):
    """
    POST /api/staff/delete/
    body: {"user_id": 123}
    Deletes a staff user (teacher/admin/etc). Protects against self-delete & superadmin.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # Only privileged users may delete staff
        role = getattr(request.user, "role", "")
        if role not in ("admin", "operator", "registrar", "accountant"):
            return Response({"detail": "Forbidden"}, status=403)

        user_id = request.data.get("user_id")
        if not user_id:
            return Response({"detail": "user_id required"}, status=400)

        try:
            user_id = int(user_id)
        except Exception:
            return Response({"detail": "user_id must be int"}, status=400)

        # No self-delete
        if user_id == request.user.id:
            return Response({"detail": "You cannot delete yourself"}, status=400)

        try:
            u = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"detail": "User not found"}, status=404)

        # Optional: protect top-level admins
        if (u.role or "") == "admin":
            return Response({"detail": "Cannot delete admin users"}, status=400)

        with transaction.atomic():
            # If the user is a teacher, clean related references (avoid FK errors)
            Teacher.objects.filter(user_id=u.id).delete()

            # If your SchoolClass has class_teacher FK -> set to null for this user’s teacher (if any)
            try:
                SchoolClass.objects.filter(class_teacher__user_id=u.id).update(class_teacher=None)
            except Exception:
                pass  # only if model exists / FK is set

            u.delete()

        return Response({"ok": True}, status=200)


# =========================
# Optional server-rendered page helper (if you want to pass flags to template)
# =========================

def grades_entry(request):
    """
    Only needed if you prefer a Django view to pass context into the grades entry template.
    If you keep using TemplateView in your main urls.py, you can remove this function safely.
    """
    return render(
        request,
        "grades/entry.html",
        {
            "allow_daily": getattr(settings, "ALLOW_DAILY_GRADES", True),
            "API_BASE": "/api",
        },
    )
