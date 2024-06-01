import re

from django.shortcuts import render
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _
from django.http import HttpResponseBadRequest
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


# Create your views here.
notification_to_sign_in_key_name = 'users.views.process_sign_in__notification'


def process_sign_up(request):
    data = {
        'name':              {'errors': [], 'value': '', 'label': _('Họ và tên')                   },
        'email':             {'errors': [], 'value': '', 'label': _('Email')                       },
        'password':          {'errors': [], 'value': '', 'label': _('Mật khẩu (tối thiểu 8 ký tự)')},
        'repeated_password': {'errors': [], 'value': '', 'label': _('Nhập lại mật khẩu')           },
        'errors': [],
        'previous_adjacent_url': '',
    }

    if request.method == 'POST':
        is_valid = True
        params = request.POST

        password = params.get('password')
        repeated_password = params.get('repeated_password')
        if not password:
            is_valid = False
            data['password']['errors'].append(_('Trường này không được để trống.'))
        elif len(password) < 8:
            is_valid = False
            data['password']['errors'].append(_('Trường này không được nhập ít hơn 8 ký tự.'))
        elif not repeated_password:
            is_valid = False
            data['repeated_password']['errors'].append(_('Trường này không được để trống.'))
        elif repeated_password != password:
            is_valid = False
            data['repeated_password']['errors'].append(_('Hai trường mật khẩu không khớp.'))
        else:
            data['password']['value'] = password

        name = params.get('name')
        if not name:
            is_valid = False
            data['name']['errors'].append(_('Trường này không được để trống.'))
        else:
            data['name']['value'] = name
            if len(name) > 255:
                is_valid = False
                data['name']['errors'].append(_('Trường này không được nhập quá 255 ký tự.'))

        email = params.get('email')
        if not email:
            is_valid = False
            data['email']['errors'].append(_('Trường này không được để trống.'))
        else:
            data['email']['value'] = email
            if len(email) > 255:
                is_valid = False
                data['email']['errors'].append(_('Trường này không được nhập quá 255 ký tự.'))
            pattern = re.compile('^'
                                 '[^@\[\]<>(),:;.\s\\\"]+'
                                 '(\.[^@\[\]<>(),:;.\s\\\"]+)*'
                                 '@'
                                 '([^@\[\]<>(),:;.\s\\\"]+\.)+'
                                 '[^@\[\]<>(),:;.\s\\\"]{2,}'
                                 '$')
            if not re.match(pattern=pattern, string=email):
                is_valid = False
                data['email']['errors'].append(_('Email không đúng định dạng.'))
            elif User.objects.filter(email=User.objects.normalize_email(email)):
                is_valid = False
                data['email']['errors'].append('Email đã được đăng ký với tài khoản khác.')

        if is_valid:
            User.objects.create_user(
                email=data['email']['value'],
                name=data['name']['value'],
                password=data['password']['value']
            )
            request.session[notification_to_sign_in_key_name] = "Đăng ký thành công"
            return redirect(to="users:sign_in")

    return render(request, template_name='users/sign_up.html', context={'data': data})


def process_sign_in(request):
    data = {
        'email': {'errors': [], 'value': '', 'label': _('Email')},
        'password': {'errors': [], 'value': '', 'label': _('Mật khẩu')},
        'errors': [],
        'previous_adjacent_url': '',
    }
    notification = ''

    if request.method == 'POST':
        is_valid = True
        params = request.POST

        password = params.get('password')
        if not password:
            is_valid = False
            data['password']['errors'].append(_('Trường này không được để trống.'))
        else:
            data['password']['value'] = password

        email = params.get('email')
        if not email:
            is_valid = False
            data['email']['errors'].append(_('Trường này không được để trống.'))
        else:
            data['email']['value'] = email

        if is_valid:
            user = authenticate(
                request,
                username=User.objects.normalize_email(data['email']['value']),
                password=data['password']['value']
            )
            if not user:
                data['errors'].append(_('Email hoặc mật khẩu không đúng.'))
            elif user.state == 'Locked':
                data['errors'].append(_('Tài khoản người dùng đã bị khóa.'))
            else:
                login(request, user)
                return redirect("/")

    elif request.method == 'GET':
        notification = request.session.get(notification_to_sign_in_key_name, '')
        request.session[notification_to_sign_in_key_name] = ''

    return render(request, template_name='users/sign_in.html', context={'data': data, 'notification': notification})


@ensure_is_not_anonymous_user
def process_logout(request):
    if request.method != 'POST':
        return HttpResponseBadRequest()

    logout(request)
    request.session[notification_to_sign_in_key_name] = "Đăng xuất thành công"
    return redirect(to="users:sign_in")


@ensure_is_not_anonymous_user
def process_change_password(request):
    prev_adj_url_key_name = 'users.views.process_change_password__previous_adjacent_url'
    data = {
        'old_password': {'errors': [],          'value': '', 'label': _('Mật khẩu cũ')          },
        'new_password': {'errors': [],          'value': '', 'label': _('Mật khẩu mới')         },
        'repeated_new_password': {'errors': [], 'value': '', 'label': _('Nhập lại mật khẩu mới')},
        'errors': [],
        'previous_adjacent_url': '',
    }

    if request.method == 'POST':
        is_valid = True
        params = request.POST

        new_password = params.get('new_password')
        repeated_new_password = params.get('repeated_new_password')
        if not new_password:
            is_valid = False
            data['new_password']['errors'].append(_('Trường này không được để trống.'))
        elif len(new_password) < 8:
            is_valid = False
            data['new_password']['errors'].append(_('Trường này không được nhập ít hơn 8 ký tự.'))
        elif not repeated_new_password:
            is_valid = False
            data['repeated_new_password']['errors'].append(_('Trường này không được để trống.'))
        elif repeated_new_password != new_password:
            is_valid = False
            data['repeated_new_password']['errors'].append(_('Hai trường mật khẩu mới không khớp.'))
        else:
            data['new_password']['value'] = new_password

        old_password = params.get('old_password')
        if not old_password:
            is_valid = False
            data['old_password']['errors'].append(_('Trường này không được để trống.'))
        elif not request.user.check_password(old_password):
            is_valid = False
            data['old_password']['errors'].append(_('Mật khẩu cũ không đúng.'))

        if is_valid:
            request.user.set_password(data['new_password']['value'])
            request.user.save()
            logout(request)
            request.session[notification_to_sign_in_key_name] = "Đổi mật khẩu thành công"
            return redirect(to="users:sign_in")

        if request.session.get(prev_adj_url_key_name):
            data['previous_adjacent_url'] = urlsafe_base64_decode(request.session[prev_adj_url_key_name]).decode('utf-8')

    elif request.method == 'GET':
        request_url = request.build_absolute_uri()
        referer_url = request.META['HTTP_REFERER']
        if referer_url and request_url != referer_url:
            request.session[prev_adj_url_key_name] = urlsafe_base64_encode(request.META['HTTP_REFERER'].encode('utf-8'))
            if request.session.get(prev_adj_url_key_name):
                data['previous_adjacent_url'] = urlsafe_base64_decode(request.session[prev_adj_url_key_name]).decode('utf-8')

    return render(request, template_name='users/change_password.html', context={'data': data})
