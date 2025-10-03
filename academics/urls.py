# academics/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    # CRUD ViewSets
    SubjectViewSet, TeacherViewSet, SchoolClassViewSet, StudentViewSet,
    ScheduleEntryViewSet, AttendanceViewSet, GradeViewSet,
    GradeScaleViewSet, GPAConfigViewSet,

    # Read-only directory/search
    ClassDirectoryViewSet, StudentDirectoryViewSet,

    # Utility / dashboards
    TeacherDashViewSet, ParentViewSet,

    # Operator & stats
    OperatorEnrollView, SchoolStatsView, StaffDirectoryView, StaffSetPasswordView, ParentDirectoryViewSet,
    StaffDeleteView,
)

app_name = "academics"

router = DefaultRouter()

# --- Core CRUD APIs ---
router.register(r'subjects', SubjectViewSet, basename='subjects')
router.register(r'teachers', TeacherViewSet, basename='teachers')
router.register(r'classes', SchoolClassViewSet, basename='classes')
router.register(r'students', StudentViewSet, basename='students')
router.register(r'schedule', ScheduleEntryViewSet, basename='schedule')
router.register(r'attendance', AttendanceViewSet, basename='attendance')
router.register(r'grades', GradeViewSet, basename='grades')
router.register(r'grade-scales', GradeScaleViewSet, basename='grade-scales')
router.register(r'gpa-config', GPAConfigViewSet, basename='gpa-config')
router.register("parents", ParentDirectoryViewSet, basename="parents")


# --- Read-only directory/search (for UI lists) ---
router.register(r'dir/classes', ClassDirectoryViewSet, basename='dir-classes')
router.register(r'dir/students', StudentDirectoryViewSet, basename='dir-students')

# --- Non-Model endpoints from ViewSets (map specific actions) ---
teacher_classes_me = TeacherDashViewSet.as_view({'get': 'my_classes'})
parent_children = ParentViewSet.as_view({'get': 'children'})
parent_child_overview = ParentViewSet.as_view({'get': 'child_overview'})

urlpatterns = [
    # Router (all viewsets, including custom @action routes like
    # /teachers/directory/, /teachers/{id}/set-password/,
    # /attendance/bulk-mark/, /classes/{id}/students_az/, etc.)
    path('', include(router.urls)),

    # Teacher dashboard helpers
    path('teacher/classes/me/', teacher_classes_me, name='teacher-classes-me'),

    # Parent helpers
    path('parent/children/', parent_children, name='parent-children'),
    path('parent/child/<int:student_id>/overview/', parent_child_overview, name='parent-child-overview'),

    # Operator enroll + School stats
    path('operator/enroll/', OperatorEnrollView.as_view(), name='operator-enroll'),
    path('stats/school/', SchoolStatsView.as_view(), name='school-stats'),
    path('staff/directory/', StaffDirectoryView.as_view(), name='staff-directory'),
    path('staff/set-password/', StaffSetPasswordView.as_view(), name='staff-set-password'),
    path('staff/delete/', StaffDeleteView.as_view(), name='staff-delete'),

]
