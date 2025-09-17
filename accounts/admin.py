from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django import forms
from .models import User

class UserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Password confirmation", widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ("phone", "first_name", "last_name", "role", "is_active", "is_staff", "is_superuser")

    def clean_password2(self):
        p1 = self.cleaned_data.get("password1")
        p2 = self.cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Passwords don't match")
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user

class UserChangeForm(forms.ModelForm):
    """Keeps password hashed; use the dedicated 'change password' action for changes."""
    class Meta:
        model = User
        fields = ("phone", "first_name", "last_name", "role",
                  "is_active", "is_staff", "is_superuser", "groups", "user_permissions")

class UserAdmin(BaseUserAdmin):
    add_form = UserCreationForm
    form = UserChangeForm
    model = User
    list_display = ("id", "phone", "first_name", "last_name", "role", "is_active", "is_staff", "is_superuser")
    list_filter = ("role", "is_active", "is_staff", "is_superuser")
    ordering = ("id",)
    search_fields = ("phone", "first_name", "last_name")

    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "role")}),
        ("Permissions", {"fields": ("is_active","is_staff","is_superuser","groups","user_permissions")}),
        ("Important dates", {"fields": ("last_login",)}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("phone","first_name","last_name","role","is_active","is_staff","is_superuser","password1","password2"),
        }),
    )

admin.site.register(User, UserAdmin)
