import datetime
from hashlib import shake_128
from random import randint

from django.db import models
from django.contrib.auth.models import BaseUserManager, AbstractBaseUser
from django.utils.translation import gettext_lazy as _


def generate_code(email):
    m = shake_128(f'{email}{randint(0, 999999)}{datetime.datetime.now(datetime.timezone.utc)}'.encode('utf-8'))
    code = f"#{m.hexdigest(3)}"
    while User.objects.filter(code=code).count():
        m.update(f'{email}{randint(0, 999999)}{datetime.datetime.now(datetime.timezone.utc)}'.encode('utf-8'))
        code = f"#{m.hexdigest(3)}"
    return code


class UserManager(BaseUserManager):
    def create_user(self, email, name, password=None):
        """
        Creates and saves a User with the given email, name and password.
        """
        if not email:
            raise ValueError(_('Người dùng phải có email.'))

        if not name:
            raise ValueError(_('Người dùng phải có họ và tên.'))

        _email = self.normalize_email(email)
        user = self.model(
            email=_email,
            name=name,
            code=generate_code(_email),
            updated_at=datetime.datetime.now(datetime.timezone.utc),
        )

        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_admin(self, email, name, password=None):
        """
        Creates and saves a superuser with the given email, name and password.
        """
        user = self.create_user(email=email, name=name, password=password, )

        user.is_staff = False
        user.role = 'Admin'
        user.save(using=self._db)
        return user

    def create_superuser(self, email, name, password=None):
        """
        Creates and saves a superuser with the given email, name and password.
        """
        user = self.create_user(email=email, name=name, password=password,)

        user.is_staff = True
        user.role = 'Admin'
        user.save(using=self._db)
        return user


class User(AbstractBaseUser):
    name = models.CharField(_('họ và tên'), max_length=255, )
    code = models.CharField(_('mã'), max_length=15, unique=True, )
    email = models.EmailField(_('email'), max_length=255, unique=True, )
    updated_at = models.DateTimeField(_('thời điểm cập nhật gần nhất'), )
    STATE_CHOICES = (
        ('Normal', _('Bình thường')),
        ('Locked', _('Đã bị khóa'))
    )
    state = models.CharField(verbose_name=_('Trạng thái'), max_length=255, choices=STATE_CHOICES, default='Normal', )
    ROLE_CHOICES = (
        ('Admin', _('Quản trị viên')),
        ('User', _('Người dùng'))
    )
    role = models.CharField(_('vai trò'), max_length=255, choices=ROLE_CHOICES, default='User')
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    def __str__(self):
        return self.email

    def has_perm(self, perm, obj=None):
        """Does the user have a specific permission?
        Simplest possible answer: Yes, always"""
        return True

    def has_module_perms(self, app_label):
        """Does the user have permissions to view the app `app_label`?
        Simplest possible answer: Yes, always"""
        return True


class Log(models.Model):
    model_name = models.CharField(verbose_name=_('tên lớp đối tượng'), max_length=255, )
    object_id = models.IntegerField(verbose_name=_('id đối tượng'), )
    user_id = models.IntegerField(verbose_name=_('id người thực hiện'), )
    content = models.TextField(verbose_name=_('nội dung thay đổi'), default='')
    created_at = models.DateTimeField(_('thời điểm tạo'), )

    objects = models.Manager()
