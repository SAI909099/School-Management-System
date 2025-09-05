from django.contrib import admin
from .models import User

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('id', 'phone', 'first_name', 'last_name', 'role', 'is_active')
    search_fields = ('phone', 'first_name', 'last_name')
    list_filter = ('role', 'is_active')