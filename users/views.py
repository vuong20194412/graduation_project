import re

from django.shortcuts import render
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.http import HttpResponseBadRequest
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

from .models import User


def ensure_is_admin(function=None):
    def wrapper(request, **kwargs):
        if request.user.is_anonymous:
            return redirect("users:sign_in")
        elif request.user.role != 'Admin':
            return HttpResponseBadRequest()
        return function(request, **kwargs)
    return wrapper


def ensure_is_not_anonymous_user(function=None):
    def wrapper(request, **kwargs):
        if request.user.is_anonymous:
            return redirect("users:sign_in")
        return function(request, **kwargs)
    return wrapper


# Create your views here.
def process_sign_up(request):
    data = {
        'name': {
            'label': _('Họ và tên'),
            'value': '',
            'errors': [],
        },
        'email': {
            'label': _('Email'),
            'value': '',
            'errors': [],
        },
        'password': {
            'label': _('Mật khẩu (tối thiểu 8 ký tự)'),
            'value': '',
            'errors': [],
        },
        'repeated_password': {
            'label': _('Nhập lại mật khẩu'),
            'value': '',
            'errors': [],
        },
        'error': '',
        'autofocus': 'name',
    }

    def valid_form_sign_up(_data):
        first_invalid = ''
        params = request.POST
        password = params.get('password')
        repeated_password = params.get('repeated_password')
        if not password:
            first_invalid = 'password'
            _data['password']['errors'].append(_('Trường này không được để trống.'))
        elif len(password) < 8:
            first_invalid = 'password'
            _data['password']['errors'].append(_('Trường này không được nhập ít hơn 8 ký tự.'))
        elif not repeated_password:
            first_invalid = 'password'
            _data['repeated_password']['errors'].append(_('Trường này không được để trống.'))
        elif repeated_password != password:
            first_invalid = 'password'
            _data['repeated_password']['errors'].append(_('Hai trường mật khẩu không khớp.'))
        else:
            _data['password']['value'] = password

        name = params.get('name')
        if not name:
            first_invalid = 'name'
            _data['name']['errors'].append(_('Trường này không được để trống.'))
        else:
            _data['name']['value'] = name
            if len(name) > 255:
                first_invalid = 'name'
                _data['name']['errors'].append(_('Trường này không được nhập quá 255 ký tự.'))

        email = params.get('email')
        if not email:
            first_invalid = 'email'
            _data['email']['errors'].append(_('Trường này không được để trống.'))
        else:
            _data['email']['value'] = email
            if len(email) > 255:
                first_invalid = 'email'
                _data['email']['errors'].append(_('Trường này không được nhập quá 255 ký tự.'))
            pattern = re.compile('^'
                                 '[^@\[\]<>(),:;.\s\\\"]+'
                                 '(\.[^@\[\]<>(),:;.\s\\\"]+)*'
                                 '@'
                                 '([^@\[\]<>(),:;.\s\\\"]+\.)+'
                                 '[^@\[\]<>(),:;.\s\\\"]{2,}'
                                 '$')
            if not re.match(pattern=pattern, string=email):
                first_invalid = 'email'
                _data['email']['errors'].append(_('Email không đúng định dạng.'))
            elif User.objects.filter(email=User.objects.normalize_email(email)):
                first_invalid = 'email'
                _data['email']['errors'].append('Email đã được đăng ký với tài khoản khác.')

        if first_invalid:
            _data['autofocus'] = first_invalid
            return _data, False
        else:
            return _data, True

    if request.method == 'POST':
        data, is_invalid = valid_form_sign_up(_data=data)
        if is_invalid:
            User.objects.create_user(
                email=data['email']['value'],
                name=data['name']['value'],
                password=data['password']['value']
            )
            return redirect(f'{reverse("users:sign_in")}?notification=sign_up_success')

    return render(request, template_name='users/sign_up.html', context={'data': data})


def process_sign_in(request):
    data = {
        'email': {
            'label': _('Email'),
            'value': '',
            'errors': [],
        },
        'password': {
            'label': _('Mật khẩu'),
            'value': '',
            'errors': [],
        },
        'error': '',
        'autofocus': 'email',
    }
    notification = ''

    def valid_form_sign_in(_data):
        first_invalid = ''
        params = request.POST
        password = params.get('password')
        if not password:
            first_invalid = 'password'
            _data['password']['errors'].append(_('Trường này không được để trống.'))
        else:
            _data['password']['value'] = password

        email = params.get('email')
        if not email:
            first_invalid = 'email'
            _data['email']['errors'].append(_('Trường này không được để trống.'))
        else:
            _data['email']['value'] = email

        if first_invalid:
            _data['autofocus'] = first_invalid
            return _data, False
        else:
            return _data, True

    if request.method == 'POST':
        data, is_invalid = valid_form_sign_in(_data=data)
        if is_invalid:
            user = authenticate(
                request,
                username=User.objects.normalize_email(data['email']['value']),
                password=data['password']['value']
            )
            if user is not None:
                login(request, user)
                return redirect("/")
            else:
                data['error'] = _('Email hoặc mật khẩu không đúng.')
                data['autofocus'] = 'password'

    elif request.method == 'GET':
        notification = request.GET.get('notification')
        if notification == 'logout_success':
            notification = 'Đăng xuất thành công'
        elif notification == 'sign_up_success':
            notification = 'Đăng ký thành công'
        elif notification == 'change_password_success':
            notification = 'Đổi mật khẩu thành công'

    return render(request, template_name='users/sign_in.html', context={'data': data, 'notification': notification})


@ensure_is_not_anonymous_user
def process_logout(request):
    if request.method == 'POST':
        logout(request)
        return redirect(f'{reverse("users:sign_in")}?notification=logout_success')

    return HttpResponseBadRequest()


@ensure_is_not_anonymous_user
def process_change_password(request):
    data = {
        'old_password': {
            'label': _('Mật khẩu cũ'),
            'errors': [],
        },
        'new_password': {
            'label': _('Mật khẩu mới'),
            'value': '',
            'errors': [],
        },
        'repeated_new_password': {
            'label': _('Nhập lại mật khẩu mới'),
            'errors': [],
        },
        'back_url': '',
        'error': '',
    }

    def valid_form_change_password(_data):
        first_invalid = ''
        params = request.POST
        new_password = params.get('new_password')
        repeated_new_password = params.get('repeated_new_password')
        if not new_password:
            first_invalid = 'new_password'
            _data['new_password']['errors'].append(_('Trường này không được để trống.'))
        elif len(new_password) < 8:
            first_invalid = 'new_password'
            _data['new_password']['errors'].append(_('Trường này không được nhập ít hơn 8 ký tự.'))
        elif not repeated_new_password:
            first_invalid = 'new_password'
            _data['repeated_new_password']['errors'].append(_('Trường này không được để trống.'))
        elif repeated_new_password != new_password:
            first_invalid = 'new_password'
            _data['repeated_new_password']['errors'].append(_('Hai trường mật khẩu mới không khớp.'))
        else:
            _data['new_password']['value'] = new_password

        old_password = params.get('old_password')
        if not old_password:
            first_invalid = 'old_password'
            _data['old_password']['errors'].append(_('Trường này không được để trống.'))
        elif not request.user.check_password(old_password):
            first_invalid = 'old_password'
            _data['old_password']['errors'].append(_('Mật khẩu cũ không đúng.'))

        if first_invalid:
            _data['autofocus'] = first_invalid
            return _data, False
        else:
            return _data, True

    if request.method == 'POST':
        data, is_valid = valid_form_change_password(_data=data)
        if is_valid:
            user = User.objects.filter(id=request.user.id)
            if user:
                user[0].set_password(data['new_password']['value'])
                user[0].save()
            logout(request)
            return redirect(f'{reverse("users:sign_in")}?notification=change_password_success')

        if 'post_change_password_back_url' in request.session:
            data['back_url'] = urlsafe_base64_decode(request.session['post_change_password_back_url']).decode('utf-8')

    elif request.method == 'GET':
        if request.META['HTTP_REFERER']:
            request.session['post_change_password_back_url'] = urlsafe_base64_encode(request.META['HTTP_REFERER'].encode('utf-8'))
            data['back_url'] = urlsafe_base64_decode(request.session['post_change_password_back_url']).decode('utf-8')

    return render(request, template_name='users/change_password.html', context={'data': data})
