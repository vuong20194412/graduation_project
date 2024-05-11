from django import forms
from django.contrib import admin
from django.contrib.auth.models import Group
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.core.exceptions import ValidationError

from .models import User


# Register your models here.
class UserCreationForm(forms.ModelForm):
    """
    A form for creating new users.
    Includes all the required fields, plus a repeated password.
    """
    password = forms.CharField(label="Password", widget=forms.PasswordInput)
    repeated_password = forms.CharField(label="Password confirmation", widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ["email", "name"]

    def clean_repeated_password(self):
        # Check that the two password entries match
        password = self.cleaned_data.get("password")
        repeated_password = self.cleaned_data.get("repeated_password")
        if password and repeated_password and password != repeated_password:
            raise ValidationError("Passwords don't match")
        return repeated_password

    def save(self, commit=True):
        # Save the provided password in hashed format
        user = super().save(commit=False)
        # user.code = generate_code()
        # user.created_on = datetime.datetime.now(datetime.timezone.utc)
        # user.updated_on = datetime.datetime.now(datetime.timezone.utc)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class UserChangeForm(forms.ModelForm):
    """A form for updating users.
    Includes all the fields on the user,
    but replaces the password field
    with administrator's disabled password hash display field.
    """
    password = ReadOnlyPasswordHashField()

    class Meta:
        model = User
        fields = ["email", "password", "name", "is_active", "role"]

    def save(self, commit=True):
        # Save the provided password in hashed format
        user = super().save(commit=False)
        # user.updated_on = datetime.datetime.now(datetime.timezone.utc)
        if commit:
            user.save()
        return user


class UserAdmin(BaseUserAdmin):
    # The forms to add and change user instances
    form = UserChangeForm
    add_form = UserCreationForm

    # The fields to be used in displaying the User model.
    # These override the definitions on the base UserAdmin
    # that reference specific fields on auth.User.
    list_display = ["email", "name", "role"]
    list_filter = ["role"]
    # readonly_fields = ("created_on", "updated_on")
    fieldsets = [
        (None, {"fields": ["email", "password"]}),
        ("Personal info", {"fields": ["name"]}),
        ("Permissions", {"fields": ["role"]}),
    ]
    # add_fieldsets is not a standard ModelAdmin attribute. UserAdmin
    # overrides get_fieldsets to use this attribute when creating a user.
    add_fieldsets = [
        (
            None,
            {
                "classes": ["wide"],
                "fields": ["email", "name", "password", "repeated_password"],
            },
        ),
    ]
    search_fields = ["id", "email"]
    ordering = ["id"]
    filter_horizontal = []


# Now register the new UserAdmin...
admin.site.register(User, UserAdmin)
# ... and, since we're not using Django's built-in permissions,
# unregister the Group model from admin.
admin.site.unregister(Group)
