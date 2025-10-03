from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from django.views.generic import TemplateView

from academics.views import SchoolStatsView

urlpatterns = [
    path('admin/', admin.site.urls),

    # API schema & docs
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    # Apps
    path('api/auth/', include('accounts.urls')),
    path('api/', include('academics.urls')),
    path('api/billing/', include('billing.urls')),

]
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns += [
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
]

from django.views.generic import TemplateView
urlpatterns += [
    path("", TemplateView.as_view(template_name="auth_login.html"), name="login"),
    path("dashboard/", TemplateView.as_view(template_name="admin-dashboard.html"), name="admin-dashboard"),
    path('teachers/', TemplateView.as_view(template_name="teacher-main.html"), name="teachers"),
    path("classes/", TemplateView.as_view(template_name="teacher-class.html"), name="classes"),
    path("jadval/", TemplateView.as_view(template_name="teacher-list.html"), name="jadval"),
    path("sozlamalar/", TemplateView.as_view(template_name="teacher-settings.html"), name="sozlamalar"),
    path("operator/teachers/", TemplateView.as_view(template_name="operator_teachers.html" ), name="operator-teachers"),
    path("operator/parents/", TemplateView.as_view(template_name="operator-parents.html" ), name="operator-parents"),



    path("otaona/", TemplateView.as_view(template_name="parents-main.html"), name="otaona"),
    path("otaona/davomat/", TemplateView.as_view(template_name="parent-davomat.html"), name="otaona-davomat"),
    path("otaona/baholar/", TemplateView.as_view(template_name="parent-baholar.html"), name="otaona-baholar"),
    path("otaona/sozlamalar/", TemplateView.as_view(template_name="parent-settings.html"), name="otaona-sozlamalar"),
    path("jadval/", TemplateView.as_view(template_name="jadval.html"), name="admin-schedule2"),
    path("users/add/", TemplateView.as_view(template_name="admin-add-user.html"), name="admin-add-user"),


    path("schedule/classes/", TemplateView.as_view(template_name="admin-schedule-classes.html"), name="admin-schedule-classes"),
    path("schedule/view/class/<int:class_id>/", TemplateView.as_view(template_name="schedule/view_class.html"),name="schedule-view-class"),
    path("schedule/view/teacher/<int:teacher_id>/",TemplateView.as_view(template_name="schedule/view_teacher.html"),name="schedule-view-teacher"),
    path("schedule/teacher/me/view/", TemplateView.as_view(template_name="public-teacher-schedule.html"),name="public-teacher-schedule-me"),

    path('grades/daily/', TemplateView.as_view(template_name='parent-daily.html'), name='grades-daily'),
    # path("grades/entry/", TemplateView.as_view(template_name="grades/entry.html"),name="grades-entry"),
    path("grades/class/", TemplateView.as_view(template_name="grades_class.html"), name="grades-class"),


    path("schedule/view/class/", TemplateView.as_view(template_name="schedule-view-class.html"),  name="schedule-view-class"),
    path("schedule/view/teacher/", TemplateView.as_view(template_name="schedule-view-teacher.html"), name="schedule-view-teacher"),


    # (nice-to-have) teacher's own read-only page

    path("moliya/", TemplateView.as_view(template_name="moliya/moliya.html"), name="moliya-main"),
    path("moliya/chiqim/", TemplateView.as_view(template_name="moliya/moliya-chiqim.html"), name="moliya-chiqim"),
    path("moliya/oyliklar/", TemplateView.as_view(template_name="moliya/moliya-oylik.html"), name="moliya-oylik"),
    path("moliya/sozlamalar/", TemplateView.as_view(template_name="moliya/moliya-sozlamalar.html"), name="moliya-sozlamalar"),
    path("moliya/tolovlar/", TemplateView.as_view(template_name="moliya/moliya-tolovlar.html"), name="moliya-tolovlar"),


    path('operator/analytics/', TemplateView.as_view(template_name='operator/operator-analytics.html'),name='operator-analytics'),
    path("operator/", TemplateView.as_view(template_name="operator/operator-reg.html"), name="operator-main"),
    path("operator/davomat/", TemplateView.as_view(template_name="operator/oper-davomat.html"), name="operator-davomat"),
    path("operator/add/", TemplateView.as_view(template_name="operator/operator-add.html"), name="operator-add"),
    path("operator/sozlamalar/", TemplateView.as_view(template_name="operator/operator-settings.html"), name="operator-settings"),


    path("students/", TemplateView.as_view( template_name="academics/students-directory.html" ), name="students-directory"),


    path("start/", TemplateView.as_view(template_name="role-redirect.html"), name="role-redirect"),

    path("classes/manage/", TemplateView.as_view(template_name="admin-class-manager.html"), name="classes-manage"),


    # 👈 Jadval page

]



from django.views.generic import TemplateView

urlpatterns += [
    # existing:
    path("grades/entry/",TemplateView.as_view(template_name="grades/entry.html",
            extra_context={"allow_daily": True, "API_BASE": "/api"},),name="grades-entry",),

    # NEW: Teacher daily-only page (locks to Kundalik)
    path("grades/entry/daily/",TemplateView.as_view(template_name="grades/entry_daily.html",extra_context={"allow_daily": True, "API_BASE": "/api"},
        ),
        name="grades-entry-daily",
    ),
]