from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SubjectViewSet, TeacherViewSet, SchoolClassViewSet, StudentViewSet

router = DefaultRouter()
router.register('subjects', SubjectViewSet)
router.register('teachers', TeacherViewSet)
router.register('classes', SchoolClassViewSet)
router.register('students', StudentViewSet)

urlpatterns = [
    path('', include(router.urls)),
]