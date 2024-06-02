import json
import re

from django.shortcuts import render
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _
from django.http import HttpResponseBadRequest
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

from .models import User


def ensure_is_admin(function=None):
    def wrapper(request, **kwargs):
        if request.user.is_anonymous or request.user.state == 'Locked':
            return redirect("users:sign_in")
        elif request.user.role != 'Admin':
            return HttpResponseBadRequest()
        return function(request, **kwargs)
    return wrapper


def ensure_is_not_anonymous_user(function=None):
    def wrapper(request, **kwargs):
        if request.user.is_anonymous or request.user.state == 'Locked':
            return redirect("users:sign_in")
        return function(request, **kwargs)
    return wrapper


def set_prev_adj_url(request):
    request_url = request.build_absolute_uri()
    referer_url = request.META['HTTP_REFERER']
    if referer_url and request_url != referer_url:
        request.session[f'{request_url}.encoded_prev_adj_url'] = urlsafe_base64_encode(referer_url.encode('utf-8'))
    encoded_prev_adj_url = request.session.get(f'{request_url}.encoded_prev_adj_url')
    return urlsafe_base64_decode(encoded_prev_adj_url).decode('utf-8') if encoded_prev_adj_url else ''


# Create your views here.
notification_to_sign_in_key_name = 'users.views.process_sign_in__notification'


def process_sign_up(request):
    if request.method == 'GET':
        data = {
            'name': {'errors': [], 'value': '', 'label': _('Họ và tên')},
            'email': {'errors': [], 'value': '', 'label': _('Email')},
            'password': {'errors': [], 'value': '', 'label': _('Mật khẩu (tối thiểu 8 ký tự)')},
            'repeated_password': {'errors': [], 'value': '', 'label': _('Nhập lại mật khẩu')},
            'errors': [],
            'previous_adjacent_url': set_prev_adj_url(request),
        }

        params = request.GET
        data_in_params = params.get('data')
        if data_in_params:
            try:
                data_in_params = json.loads(urlsafe_base64_decode(data_in_params).decode('utf-8'))
                if 'name' in data_in_params and isinstance(data_in_params['name'], dict):
                    name_errors = data_in_params['name'].get('errors')
                    if name_errors and isinstance(name_errors, type(data['name']['errors'])):
                        for name_error in name_errors:
                            data['name']['errors'].append(_(name_error))
                    name_value = data_in_params['name'].get('value')
                    if name_value and isinstance(name_value, type(data['name']['value'])):
                        data['name']['value'] = name_value
                if 'email' in data_in_params and isinstance(data_in_params['email'], dict):
                    email_errors = data_in_params['email'].get('errors')
                    if email_errors and isinstance(email_errors, type(data['email']['errors'])):
                        for email_error in email_errors:
                            data['email']['errors'].append(_(email_error))
                    email_value = data_in_params['email'].get('value')
                    if email_value and isinstance(email_value, type(data['email']['value'])):
                        data['email']['value'] = email_value
                if 'password' in data_in_params and isinstance(data_in_params['password'], dict):
                    password_errors = data_in_params['password'].get('errors')
                    if password_errors and isinstance(password_errors, type(data['password']['errors'])):
                        for password_error in password_errors:
                            data['password']['errors'].append(_(password_error))
                if 'repeated_password' in data_in_params and isinstance(data_in_params['repeated_password'], dict):
                    repeated_password_errors = data_in_params['repeated_password'].get('errors')
                    if repeated_password_errors and isinstance(repeated_password_errors, type(data['repeated_password']['errors'])):
                        for repeated_password_error in repeated_password_errors:
                            data['repeated_password']['errors'].append(_(repeated_password_error))
                data_errors = data_in_params.get('errors')
                if data_errors and isinstance(data_errors, type(data['errors'])):
                    data['errors'] = data_errors
            except (UnicodeDecodeError, ValueError):
                pass

        return render(request, template_name='users/sign_up.html', context={'data': data})

    elif request.method == 'POST':
        data = {
            'name': {'errors': [], 'value': ''},
            'email': {'errors': [], 'value': ''},
            'password': {'errors': []},
            'repeated_password': {'errors': []},
            'errors': [],
        }

        is_valid = True
        params = request.POST

        password = params.get('password')
        repeated_password = params.get('repeated_password')
        if not password:
            is_valid = False
            data['password']['errors'].append('Trường này không được để trống.')
        elif len(password) < 8:
            is_valid = False
            data['password']['errors'].append('Trường này không được nhập ít hơn 8 ký tự.')
        elif not repeated_password:
            is_valid = False
            data['repeated_password']['errors'].append('Trường này không được để trống.')
        elif repeated_password != password:
            is_valid = False
            data['repeated_password']['errors'].append('Hai trường mật khẩu không khớp.')

        data['name']['value'] = params.get('name', '')
        name = data['name']['value'].strip()
        if not name:
            is_valid = False
            data['name']['errors'].append('Trường này không được để trống.')
        else:
            if len(name) > 255:
                is_valid = False
                data['name']['errors'].append('Trường này không được nhập quá 255 ký tự.')

        data['email']['value'] = params.get('email', '')
        email = data['email']['value'].strip()
        if not email:
            is_valid = False
            data['email']['errors'].append('Trường này không được để trống.')
        else:
            if len(email) > 255:
                is_valid = False
                data['email']['errors'].append('Trường này không được nhập quá 255 ký tự.')
            pattern = re.compile('^'
                                 '[^@\[\]<>(),:;.\s\\\"]+'
                                 '(\.[^@\[\]<>(),:;.\s\\\"]+)*'
                                 '@'
                                 '([^@\[\]<>(),:;.\s\\\"]+\.)+'
                                 '[^@\[\]<>(),:;.\s\\\"]{2,}'
                                 '$')
            if not re.match(pattern=pattern, string=email):
                is_valid = False
                data['email']['errors'].append('Email không đúng định dạng.')
            elif User.objects.filter(email=User.objects.normalize_email(email)):
                is_valid = False
                data['email']['errors'].append('Email đã được đăng ký với tài khoản khác.')

        if is_valid:
            User.objects.create_user(email=email, name=name, password=password)
            request.session[notification_to_sign_in_key_name] = _("Thực hiện đăng ký thành công")
            return redirect(to="users:sign_in")

        data_in_params = urlsafe_base64_encode(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        return redirect(to=f"{reverse('users:sign_up')}?data={data_in_params}")

    else:
        return HttpResponseBadRequest()


def process_sign_in(request):
    if request.method == 'GET':
        notification = request.session.get(notification_to_sign_in_key_name, '')
        request.session[notification_to_sign_in_key_name] = ''

        data = {
            'email': {'errors': [], 'value': '', 'label': _('Email')},
            'password': {'errors': [], 'value': '', 'label': _('Mật khẩu')},
            'errors': [],
            'previous_adjacent_url': set_prev_adj_url(request),
        }

        params = request.GET
        data_in_params = params.get('data')
        if data_in_params:
            try:
                data_in_params = json.loads(urlsafe_base64_decode(data_in_params).decode('utf-8'))
                if 'email' in data_in_params and isinstance(data_in_params['email'], dict):
                    email_errors = data_in_params['email'].get('errors')
                    if email_errors and isinstance(email_errors, type(data['email']['errors'])):
                        for email_error in email_errors:
                            data['email']['errors'].append(_(email_error))
                    email_value = data_in_params['email'].get('value')
                    if email_value and isinstance(email_value, type(data['email']['value'])):
                        data['email']['value'] = email_value
                if 'password' in data_in_params and isinstance(data_in_params['password'], dict):
                    password_errors = data_in_params['password'].get('errors')
                    if password_errors and isinstance(password_errors, type(data['password']['errors'])):
                        for password_error in password_errors:
                            data['password']['errors'].append(_(password_error))
                data_errors = data_in_params.get('errors')
                if data_errors and isinstance(data_errors, type(data['errors'])):
                    data['errors'] = data_errors
            except (UnicodeDecodeError, ValueError):
                pass

        return render(request, template_name='users/sign_in.html', context={'notification': notification, 'data': data})

    elif request.method == 'POST':
        data = {
            'email': {'errors': [], 'value': ''},
            'password': {'errors': []},
            'errors': [],
        }

        is_valid = True
        params = request.POST

        password = params.get('password')
        if not password:
            is_valid = False
            data['password']['errors'].append('Trường này không được để trống.')

        data['email']['value'] = params.get('email', '')
        email = data['email']['value'].strip()
        if not email:
            is_valid = False
            data['email']['errors'].append('Trường này không được để trống.')

        if is_valid:
            user = authenticate(request, username=User.objects.normalize_email(email), password=password)
            if not user:
                data['errors'].append('Email hoặc mật khẩu không đúng.')
            elif user.state == 'Locked':
                data['errors'].append('Tài khoản người dùng đã bị khóa.')
            else:
                login(request, user)
                return redirect("/")

        data_in_params = urlsafe_base64_encode(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        return redirect(to=f"{reverse('users:sign_in')}?data={data_in_params}")

    else:
        return HttpResponseBadRequest()


@ensure_is_not_anonymous_user
def process_logout(request):
    if request.method != 'POST':
        return HttpResponseBadRequest()

    logout(request)
    request.session[notification_to_sign_in_key_name] = _("Thực hiện đăng xuất thành công")
    return redirect(to="users:sign_in")


@ensure_is_not_anonymous_user
def process_change_password(request):
    if request.method == 'GET':
        data = {
            'old_password': {'errors': [], 'value': '', 'label': _('Mật khẩu cũ')},
            'new_password': {'errors': [], 'value': '', 'label': _('Mật khẩu mới')},
            'repeated_new_password': {'errors': [], 'value': '', 'label': _('Nhập lại mật khẩu mới')},
            'errors': [],
            'previous_adjacent_url': set_prev_adj_url(request),
        }

        params = request.GET
        data_in_params = params.get('data')
        if data_in_params:
            try:
                data_in_params = json.loads(urlsafe_base64_decode(data_in_params).decode('utf-8'))
                if 'old_password' in data_in_params and isinstance(data_in_params['old_password'], dict):
                    old_password_errors = data_in_params['old_password'].get('errors')
                    if old_password_errors and isinstance(old_password_errors, type(data['old_password']['errors'])):
                        for old_password_error in old_password_errors:
                            data['old_password']['errors'].append(_(old_password_error))
                if 'new_password' in data_in_params and isinstance(data_in_params['new_password'], dict):
                    new_password_errors = data_in_params['new_password'].get('errors')
                    if new_password_errors and isinstance(new_password_errors, type(data['new_password']['errors'])):
                        for new_password_error in new_password_errors:
                            data['new_password']['errors'].append(_(new_password_error))
                if 'repeated_new_password' in data_in_params and isinstance(data_in_params['repeated_new_password'], dict):
                    repeated_new_password_errors = data_in_params['repeated_new_password'].get('errors')
                    if repeated_new_password_errors and isinstance(repeated_new_password_errors, type(data['repeated_new_password']['errors'])):
                        for repeated_new_password_error in repeated_new_password_errors:
                            data['repeated_new_password']['errors'].append(_(repeated_new_password_error))
                data_errors = data_in_params.get('errors')
                if data_errors and isinstance(data_errors, type(data['errors'])):
                    data['errors'] = data_errors
            except (UnicodeDecodeError, ValueError):
                pass

        return render(request, template_name='users/change_password.html', context={'data': data})

    elif request.method == 'POST':
        data = {
            'old_password': {'errors': []},
            'new_password': {'errors': []},
            'repeated_new_password': {'errors': []},
            'errors': [],
        }

        is_valid = True
        params = request.POST

        new_password = params.get('new_password')
        repeated_new_password = params.get('repeated_new_password')
        if not new_password:
            is_valid = False
            data['new_password']['errors'].append('Trường này không được để trống.')
        elif len(new_password) < 8:
            is_valid = False
            data['new_password']['errors'].append('Trường này không được nhập ít hơn 8 ký tự.')
        elif not repeated_new_password:
            is_valid = False
            data['repeated_new_password']['errors'].append('Trường này không được để trống.')
        elif repeated_new_password != new_password:
            is_valid = False
            data['repeated_new_password']['errors'].append('Hai trường mật khẩu mới không khớp.')

        old_password = params.get('old_password')
        if not old_password:
            is_valid = False
            data['old_password']['errors'].append('Trường này không được để trống.')
        elif not request.user.check_password(old_password):
            is_valid = False
            data['old_password']['errors'].append('Mật khẩu cũ không đúng.')

        if is_valid:
            request.user.set_password(new_password)
            request.user.save()
            logout(request)
            request.session[notification_to_sign_in_key_name] = _("Đổi mật khẩu thành công")
            return redirect(to="users:sign_in")

        data_in_params = urlsafe_base64_encode(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        return redirect(to=f"{reverse('users:sign_in')}?data={data_in_params}")

    else:
        return HttpResponseBadRequest()
