from collections import defaultdict
from datetime import date, timedelta

from django.db.models import Avg, Q
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    StudentGuardian, ScheduleEntry, Attendance, Grade, GradeScale, GPAConfig,
    Subject, Teacher, SchoolClass, Student
)
from .permissions import IsAdminOrRegistrarWrite, IsAdminOrTeacherWrite
from .serializers import (
    ScheduleEntrySerializer, AttendanceSerializer, GradeSerializer,
    GradeScaleSerializer, GPAConfigSerializer,
    SubjectSerializer, TeacherSerializer, SchoolClassSerializer, StudentSerializer
)


# ---- CRUD ----

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

    @action(detail=True, methods=['get'])
    def students_az(self, request, pk=None):
        students = Student.objects.filter(clazz_id=pk).order_by('last_name', 'first_name')
        return Response(StudentSerializer(students, many=True).data)

    def _week_range(self, anchor: date):
        # Monday..Saturday (6 days)
        start = anchor - timedelta(days=anchor.weekday())  # Monday
        end = start + timedelta(days=5)
        return start, end

    @action(detail=True, methods=['get'])
    def attendance_grid(self, request, pk=None):
        # ?week_of=YYYY-MM-DD (any day within the week)
        d = request.query_params.get('week_of')
        anchor = date.fromisoformat(d) if d else date.today()
        start, end = self._week_range(anchor)
        students = list(Student.objects.filter(clazz_id=pk)
                        .order_by('last_name', 'first_name').values('id', 'first_name', 'last_name'))
        att = Attendance.objects.filter(clazz_id=pk, date__range=(start, end))
        grid = defaultdict(dict)
        for a in att:
            grid[a.student_id][a.date.isoformat()] = a.status
        days = [(start + timedelta(days=i)).isoformat() for i in range(6)]
        return Response({'students': students, 'days': days, 'grid': grid})

    @action(detail=True, methods=['get'])
    def gradebook_daily(self, request, pk=None):
        d = request.query_params.get('week_of')
        anchor = date.fromisoformat(d) if d else date.today()
        start, end = self._week_range(anchor)
        students = list(Student.objects.filter(clazz_id=pk)
                        .order_by('last_name', 'first_name').values('id', 'first_name', 'last_name'))
        grades = Grade.objects.filter(student__clazz_id=pk, type='daily', date__range=(start, end))
        grid = defaultdict(lambda: defaultdict(list))  # student -> day -> [scores]
        for g in grades:
            grid[g.student_id][g.date.isoformat()].append(g.score)
        days = [(start + timedelta(days=i)).isoformat() for i in range(6)]
        grid_avg = {sid: {day: (sum(vals)/len(vals) if vals else None) for day, vals in daymap.items()}
                    for sid, daymap in grid.items()}
        return Response({'students': students, 'days': days, 'grid': grid_avg})

    @action(detail=True, methods=['get'])
    def gradebook_exams(self, request, pk=None):
        term = request.query_params.get('term', '')
        grades = Grade.objects.filter(student__clazz_id=pk, type='exam')
        if term:
            grades = grades.filter(term=term)
        data = defaultdict(list)
        for g in grades.order_by('date'):
            data[g.student_id].append({'subject': g.subject_id, 'date': g.date, 'score': g.score})
        return Response(data)

    @action(detail=True, methods=['get'])
    def gradebook_final(self, request, pk=None):
        term = request.query_params.get('term', '')
        grades = Grade.objects.filter(student__clazz_id=pk, type='final')
        if term:
            grades = grades.filter(term=term)
        data = defaultdict(list)
        for g in grades.order_by('date'):
            data[g.student_id].append({'subject': g.subject_id, 'date': g.date, 'score': g.score})
        return Response(data)

    @action(detail=True, methods=['get'])
    def gpa_ranking(self, request, pk=None):
        term = request.query_params.get('term', '')
        scale = _active_scale()
        weights = _active_weights()
        students = Student.objects.filter(clazz_id=pk)
        result = []
        for s in students:
            subj_ids = Subject.objects.values_list('id', flat=True)
            subj_gpas = []
            for sub in subj_ids:
                q = Q(student=s, subject_id=sub)
                if term:
                    q &= Q(term=term)
                g_daily = Grade.objects.filter(q & Q(type='daily')).aggregate(avg=Avg('score'))['avg']
                g_exam  = Grade.objects.filter(q & Q(type='exam')).aggregate(avg=Avg('score'))['avg']
                g_final = Grade.objects.filter(q & Q(type='final')).aggregate(avg=Avg('score'))['avg']
                def gp(x):
                    if not x:
                        return None
                    return float(scale.point_for(round(x)))
                parts = [
                    (gp(g_daily), float(weights.weight_daily)),
                    (gp(g_exam),  float(weights.weight_exam)),
                    (gp(g_final), float(weights.weight_final)),
                ]
                if any(p[0] is not None for p in parts):
                    total = sum((p*w for p, w in parts if p is not None))
                    wsum  = sum((w for p, w in parts if p is not None))
                    subj_gpas.append(total/wsum if wsum else 0)
            overall = sum(subj_gpas)/len(subj_gpas) if subj_gpas else 0.0
            result.append({'student_id': s.id,
                           'name': f"{s.last_name} {s.first_name}",
                           'gpa': round(overall, 2)})
        result.sort(key=lambda x: x['gpa'], reverse=True)
        for idx, r in enumerate(result, start=1):
            r['rank'] = idx
        return Response({'class_id': pk, 'ranking': result})


class StudentViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.select_related('clazz').all()
    serializer_class = StudentSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarWrite]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, 'role', None) == 'teacher':
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
        if getattr(user, 'role', None) != 'teacher':
            return Response([])
        try:
            teacher = user.teacher_profile
        except Teacher.DoesNotExist:
            return Response([])
        students = Student.objects.filter(clazz__class_teacher=teacher)
        return Response(StudentSerializer(students, many=True).data)


class ScheduleEntryViewSet(viewsets.ModelViewSet):
    queryset = ScheduleEntry.objects.select_related('clazz', 'teacher', 'subject').all()
    serializer_class = ScheduleEntrySerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarWrite]

    @action(detail=False, methods=['get'], url_path='class/(?P<class_id>[^/.]+)')
    def by_class(self, request, class_id=None):
        qs = self.queryset.filter(clazz_id=class_id).order_by('weekday', 'start_time')
        return Response(self.serializer_class(qs, many=True).data)

    @action(detail=False, methods=['get'], url_path='teacher/me')
    def my_schedule(self, request):
        user = request.user
        if getattr(user, 'role', None) != 'teacher':
            return Response([])
        try:
            t = user.teacher_profile
        except Teacher.DoesNotExist:
            return Response([])
        qs = self.queryset.filter(teacher=t)
        return Response(self.serializer_class(qs, many=True).data)

    @action(detail=False, methods=['get'], url_path='teacher/(?P<teacher_id>[^/.]+)')
    def by_teacher_id(self, request, teacher_id=None):
        qs = self.queryset.filter(teacher_id=teacher_id).order_by('weekday', 'start_time')
        return Response(self.serializer_class(qs, many=True).data)

    def get_queryset(self):
        qs = super().get_queryset()
        teacher_id = self.request.query_params.get('teacher')
        class_id = self.request.query_params.get('clazz') or self.request.query_params.get('class')
        if teacher_id:
            qs = qs.filter(teacher_id=teacher_id)
        if class_id:
            qs = qs.filter(clazz_id=class_id)
        return qs.order_by('weekday', 'start_time')


class AttendanceViewSet(viewsets.ModelViewSet):
    queryset = Attendance.objects.select_related('student', 'clazz', 'subject', 'teacher').all()
    serializer_class = AttendanceSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrTeacherWrite]

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        role = getattr(u, 'role', None)
        if role == 'teacher':
            try:
                t = u.teacher_profile
                qs = qs.filter(Q(clazz__class_teacher=t) | Q(teacher=t))
            except Teacher.DoesNotExist:
                return Attendance.objects.none()
        elif role == 'parent':
            child_ids = StudentGuardian.objects.filter(guardian=u).values_list('student_id', flat=True)
            qs = qs.filter(student_id__in=child_ids)
        return qs

    @action(detail=False, methods=['post'], url_path='bulk-mark')
    def bulk_mark(self, request):
        """
        Payload:
        {
          "class": <id>, "date": "YYYY-MM-DD",
          "subject": <id or null>,
          "entries": [{"student":id, "status":"present|absent|late|excused", "note":""}]
        }
        """
        u = request.user
        if getattr(u, 'role', None) not in ('admin', 'teacher'):
            return Response({'detail': 'Forbidden'}, status=403)
        clazz = request.data.get('class')
        dt = request.data.get('date')
        subject = request.data.get('subject')
        entries = request.data.get('entries', [])
        try:
            t = u.teacher_profile if getattr(u, 'role', None) == 'teacher' else None
        except Teacher.DoesNotExist:
            t = None
        ids = []
        for e in entries:
            obj, _ = Attendance.objects.update_or_create(
                student_id=e['student'], date=dt, subject_id=subject,
                defaults={'status': e['status'], 'note': e.get('note', ''), 'clazz_id': clazz, 'teacher': t}
            )
            ids.append(obj.id)
        return Response({'ok': True, 'ids': ids})


class GradeViewSet(viewsets.ModelViewSet):
    queryset = Grade.objects.select_related('student', 'subject', 'teacher').all()
    serializer_class = GradeSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrTeacherWrite]

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        role = getattr(u, 'role', None)
        if role == 'teacher':
            try:
                t = u.teacher_profile
                qs = qs.filter(Q(student__clazz__class_teacher=t) | Q(teacher=t))
            except Teacher.DoesNotExist:
                return Grade.objects.none()
        elif role == 'parent':
            child_ids = StudentGuardian.objects.filter(guardian=u).values_list('student_id', flat=True)
            qs = qs.filter(student_id__in=child_ids)
        return qs

    @action(detail=False, methods=['post'], url_path='bulk-set')
    def bulk_set(self, request):
        """
        Payload:
        {
          "class": id, "date":"YYYY-MM-DD", "subject": id,
          "type":"daily|exam|final", "term":"2025-1",
          "entries":[{"student":id, "score":2..5, "comment":""}]
        }
        """
        u = request.user
        if getattr(u, 'role', None) not in ('admin', 'teacher'):
            return Response({'detail': 'Forbidden'}, status=403)
        data = request.data
        t = None
        if getattr(u, 'role', None) == 'teacher':
            try:
                t = u.teacher_profile
            except Teacher.DoesNotExist:
                pass
        ids = []
        for e in data.get('entries', []):
            obj, _ = Grade.objects.update_or_create(
                student_id=e['student'],
                subject_id=data['subject'],
                date=data['date'],
                type=data['type'],
                defaults={
                    'score': e['score'],
                    'comment': e.get('comment', ''),
                    'teacher': t,
                    'term': data.get('term', '')
                }
            )
            ids.append(obj.id)
        return Response({'ok': True, 'ids': ids})

    @action(detail=False, methods=['get'], url_path='by-class')
    def by_class(self, request):
        """
        Read-only filter:
        GET /api/grades/by-class/?class=<id>&subject=<id>&type=daily|exam|final&date=YYYY-MM-DD&term=2025-1
        Returns: list of grades for the class that match the filters.
        Role rules are applied (teacher sees own domain, parent sees own kids, etc).
        """
        qs = self.get_queryset()
        clazz = request.query_params.get('class')
        subject = request.query_params.get('subject')
        gtype = request.query_params.get('type')
        date = request.query_params.get('date')
        term = request.query_params.get('term', '')

        if clazz:
            qs = qs.filter(student__clazz_id=clazz)
        if subject:
            qs = qs.filter(subject_id=subject)
        if gtype:
            qs = qs.filter(type=gtype)
        if date:
            qs = qs.filter(date=date)
        if term:
            qs = qs.filter(term=term)

        # Return minimal payload needed to prefill
        data = qs.values('student_id', 'score', 'comment')
        return Response(list(data))


# ---- GPA helpers ----

def _active_scale():
    return GradeScale.objects.filter(active=True).first() or GradeScale.objects.create()


def _active_weights():
    return GPAConfig.objects.filter(active=True).first() or GPAConfig.objects.create()


# ---- Dashboards / Parent ----

class TeacherDashViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'], url_path='classes/me')
    def my_classes(self, request):
        u = request.user
        if getattr(u, 'role', None) != 'teacher':
            return Response([])
        try:
            t = u.teacher_profile
        except Teacher.DoesNotExist:
            return Response([])
        classes = SchoolClass.objects.filter(Q(class_teacher=t) | Q(schedule__teacher=t)).distinct().order_by('name')
        return Response(SchoolClassSerializer(classes, many=True).data)


class ParentViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'], url_path='children')
    def children(self, request):
        u = request.user
        if getattr(u, 'role', None) != 'parent':
            return Response([])
        child_ids = StudentGuardian.objects.filter(guardian=u).values_list('student_id', flat=True)
        kids = Student.objects.filter(id__in=child_ids).order_by('last_name', 'first_name')
        return Response(StudentSerializer(kids, many=True).data)

    @action(detail=False, methods=['get'], url_path='child/(?P<student_id>[^/.]+)/overview')
    def child_overview(self, request, student_id=None):
        u = request.user
        if getattr(u, 'role', None) != 'parent':
            return Response({'detail': 'Forbidden'}, status=403)
        if not StudentGuardian.objects.filter(guardian=u, student_id=student_id).exists():
            return Response({'detail': 'Forbidden'}, status=403)
        s = Student.objects.select_related('clazz').get(id=student_id)
        timetable = ScheduleEntry.objects.filter(clazz=s.clazz).order_by('weekday', 'start_time')

        # latest week Mon..Sat
        today = date.today()
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=5)
        latest_att = Attendance.objects.filter(student=s, date__range=(start, end))

        # grades summary per subject
        scale = _active_scale()
        weights = _active_weights()
        summary = {}
        for sub in Subject.objects.all():
            g_daily = Grade.objects.filter(student=s, subject=sub, type='daily').aggregate(avg=Avg('score'))['avg']
            g_exam  = Grade.objects.filter(student=s, subject=sub, type='exam').aggregate(avg=Avg('score'))['avg']
            g_final = Grade.objects.filter(student=s, subject=sub, type='final').aggregate(avg=Avg('score'))['avg']

            def gp(x):
                return float(scale.point_for(round(x))) if x else None

            parts = [
                (gp(g_daily), float(weights.weight_daily)),
                (gp(g_exam),  float(weights.weight_exam)),
                (gp(g_final), float(weights.weight_final)),
            ]
            if any(p[0] is not None for p in parts):
                total = sum((p*w for p, w in parts if p is not None))
                wsum  = sum((w for p, w in parts if p is not None))
                subject_gpa = total/wsum if wsum else 0
                summary[sub.name] = {
                    'daily_avg': round(g_daily, 2) if g_daily else None,
                    'exam_avg':  round(g_exam, 2) if g_exam else None,
                    'final_avg': round(g_final, 2) if g_final else None,
                    'gpa_subject': round(subject_gpa, 2),
                }

        # overall GPA and rank in class
        ranking = SchoolClassViewSet().gpa_ranking(request, pk=s.clazz_id).data['ranking']
        overall = next((r['gpa'] for r in ranking if r['student_id'] == s.id), 0.0)
        rank = next((r['rank'] for r in ranking if r['student_id'] == s.id), None)

        payload = {
            'student': StudentSerializer(s).data,
            'class_name': s.clazz.name if s.clazz else '',
            'timetable': ScheduleEntrySerializer(timetable, many=True).data,
            'latest_week_attendance': AttendanceSerializer(latest_att, many=True).data,
            'grades_summary': summary,
            'gpa_overall': round(overall, 2),
            'class_rank': rank,
            'class_size': s.clazz.students.count() if s.clazz else 0,
        }
        return Response(payload)


from rest_framework import viewsets, permissions
from .models import GradeScale, GPAConfig
from .serializers import GradeScaleSerializer, GPAConfigSerializer
from .permissions import IsAdminOrRegistrarWrite

class GradeScaleViewSet(viewsets.ModelViewSet):
    queryset = GradeScale.objects.all()
    serializer_class = GradeScaleSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarWrite]

class GPAConfigViewSet(viewsets.ModelViewSet):
    queryset = GPAConfig.objects.all()
    serializer_class = GPAConfigSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrRegistrarWrite]
