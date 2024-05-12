import datetime
from math import ceil as math_ceil
import re

from django.db.models import Count
from django.shortcuts import render, get_object_or_404
from django.contrib.auth import get_user_model
from django.shortcuts import redirect
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.http import HttpResponseBadRequest, HttpResponseNotFound, Http404
from django.utils import timezone

from .models import QuestionTag, Question, Answer, Comment, CommentEvaluation, QuestionEvaluation
from users.views import ensure_is_not_anonymous_user, ensure_is_admin
from users.models import Log


def convert_to_int(string: str, default: int = 0):
    return int(string) if re.match(string=string, pattern=re.compile('^-?[0-9]+$')) else default


def convert_to_non_negative_int(string: str, default: int = 0):
    return int(string) if re.match(string=string, pattern=re.compile('^[0-9]+$')) else default


def view_questions(request, path_name, function_filter=None, notification=''):
    params = request.GET

    tags = QuestionTag.objects.all()
    if tags:
        tag_id = convert_to_non_negative_int(string=(params.get('tid') or ''), default=tags[0].id)
        if not tags.filter(id=tag_id):
            tag_id = tags[0].id
    else:
        raise Http404()

    limit = convert_to_non_negative_int(string=(params.get('limit') or ''), default=4) or 4

    if (params.get('type') or '') == 'is_filters_and_sorters':
        request.session[f'{path_name}__filters_and_sorters'] = {
            'filter_by_created_at_from': params.get('filter_by_created_at_from'),
            'filter_by_created_at_to': params.get('filter_by_created_at_to'),
            'filter_by_title': params.get('filter_by_title'),
            'filter_by_author': params.get('filter_by_author'),
            'sorter_with_created_at': params.get('sorter_with_created_at'),
            'sorter_with_title': params.get('sorter_with_title'),
            'sorter_with_decreasing_number_of_answers': params.get('sorter_with_decreasing_number_of_answers'),
            'sorter_with_decreasing_number_of_comments': params.get('sorter_with_decreasing_number_of_comments'),
        }
    elif not request.session.get(f'{path_name}__filters_and_sorters'):
        request.session[f'{path_name}__filters_and_sorters'] = {
            'filter_by_created_at_from': '',
            'filter_by_created_at_to': '',
            'filter_by_title': '',
            'filter_by_author': '',
            'sorter_with_created_at': '',
            'sorter_with_title': '',
            'sorter_with_decreasing_number_of_answers': False,
            'sorter_with_decreasing_number_of_comments': False,
        }

    _filters_and_sorters = request.session.get(f'{path_name}__filters_and_sorters')

    kfilter = {'tag_id': tag_id, }
    created_at_from = _filters_and_sorters['filter_by_created_at_from']
    if created_at_from:
        kfilter['created_at__gte'] = datetime.datetime.strptime(created_at_from + ':00.000000', '%Y-%m-%dT%H:%M:%S.%f')
    created_at_to = _filters_and_sorters['filter_by_created_at_to']
    if created_at_to:
        kfilter['created_at__lte'] = datetime.datetime.strptime(created_at_to + ':59.999999', '%Y-%m-%dT%H:%M:%S.%f')
    titles = _filters_and_sorters['filter_by_title']
    if titles:
        kfilter['title__iregex'] = r"^[^,]*" + ('|'.join([title.strip() for title in titles.split(',')])) + r"[^,]*$"
    authors = _filters_and_sorters['filter_by_author']
    if authors:
        kfilter['user__name__iregex'] = r"^[^,]*" + (
            '|'.join([author.strip() for author in authors.split(',')])) + r"[^,]*$"

    order_by = {'sorter': [], 'kalias': {}}
    order_created_at = _filters_and_sorters['sorter_with_created_at']
    if order_created_at and order_created_at in ('+', '-'):
        order_by['sorter'].append('-created_at' if order_created_at == '-' else 'created_at')
    order_title = _filters_and_sorters['sorter_with_title']
    if order_title and order_title in ('+', '-'):
        order_by['sorter'].append('-title' if order_title == '-' else 'title')
    if _filters_and_sorters['sorter_with_decreasing_number_of_answers']:
        order_by['kalias']['answer__count'] = Count('answer')
        order_by['sorter'].append('-answer__count')
    if _filters_and_sorters['sorter_with_decreasing_number_of_comments']:
        order_by['kalias']['comment__count'] = Count('comment')
        order_by['sorter'].append('-comment__count')

    page_count = math_ceil(function_filter(user_id=request.user.id, begin=0, count=True, kfilter=kfilter) / limit) or 1

    page_offset = convert_to_int(string=(params.get('offset') or ''), default=1)
    if page_offset > 1:
        page_offset = page_offset if page_offset < page_count else page_count
    else:
        page_offset = page_count if page_offset == -1 else 1
    offset = (page_offset - 1) * limit

    questions = function_filter(user_id=request.user.id,
                                begin=offset,
                                end=offset + limit,
                                order_by=order_by,
                                kfilter=kfilter)

    context = {
        "questions": questions,
        "page_range": range(1, page_count + 1),
        "tags": tags,
        "question_conditions": {
            "path_name": path_name,
            "tag_id": tag_id,
            "page_offset": page_offset,
            "limit": limit,
            'filter_by_created_at_from': _filters_and_sorters.get('filter_by_created_at_from'),
            'filter_by_created_at_to': _filters_and_sorters.get('filter_by_created_at_to'),
            'filter_by_title': _filters_and_sorters.get('filter_by_title'),
            'filter_by_author': _filters_and_sorters.get('filter_by_author'),
            'sorter_with_created_at': _filters_and_sorters.get('sorter_with_created_at'),
            'sorter_with_title': _filters_and_sorters.get('sorter_with_title'),
            'sorter_with_decreasing_number_of_answers': _filters_and_sorters.get(
                'sorter_with_decreasing_number_of_answers'),
            'sorter_with_decreasing_number_of_comments': _filters_and_sorters.get(
                'sorter_with_decreasing_number_of_comments'),
        },
        "suffix_utc": '' if not timezone.get_current_timezone_name() == 'UTC' else 'UTC',
        "logout_link": reverse('users:logout'),
        "change_password_link": reverse('users:change_password'),
        "notification": notification,
    }

    return render(request, template_name='practice/questions.html', context=context)


@ensure_is_not_anonymous_user
def view_created_questions(request):
    def filter_created_questions(user_id: int, begin: int, end: int = None, count: int = False,
                                 order_by: dict = None, kfilter: dict = None):
        if not isinstance(kfilter, dict):
            kfilter = {}
        kfilter['user_id'] = user_id
        if count:
            return Question.objects.filter(**kfilter).count()
        elif isinstance(order_by, dict):
            kalias = order_by.get('kalias') or {}
            order_by = order_by.get('sorter') or []
            if end is not None:
                return Question.objects.filter(**kfilter).alias(**kalias).order_by(*order_by)[begin:end]
            return Question.objects.filter(**kfilter).alias(**kalias).order_by(*order_by)[begin:]
        else:
            if end is not None:
                return Question.objects.filter(**kfilter)[begin:end]
            return Question.objects.filter(**kfilter)[begin:]

    notification = ''
    if request.method == 'GET':
        if (request.GET.get('notification') or '') == 'create_question_success':
            notification = 'Tạo câu hỏi thành công'

    return view_questions(request=request,
                          path_name='practice:view_created_questions',
                          function_filter=filter_created_questions,
                          notification=notification)


@ensure_is_not_anonymous_user
def view_answered_questions(request):
    def filter_answered_questions(user_id: int, begin: int, end: int = None, count: int = False,
                                  order_by: dict = None, kfilter: dict = None):
        if not isinstance(kfilter, dict):
            kfilter = {}
        kfilter['answer__user_id'] = user_id
        if get_user_model().objects.filter(id=user_id).exclude(role='Admin'):
            kfilter['state'] = 'Approved'
        if count:
            return Question.objects.filter(**kfilter).count()
        elif isinstance(order_by, dict):
            kalias = order_by.get('kalias') or {}
            order_by = order_by.get('sorter') or []
            if end is not None:
                return Question.objects.filter(**kfilter).alias(**kalias).order_by(*order_by)[begin:end]
            return Question.objects.filter(**kfilter).alias(**kalias).order_by(*order_by)[begin:]
        else:
            if end is not None:
                return Question.objects.filter(**kfilter)[begin:end]
            return Question.objects.filter(**kfilter)[begin:]

    return view_questions(request=request,
                          path_name='practice:view_answered_questions',
                          function_filter=filter_answered_questions)


@ensure_is_not_anonymous_user
def view_unanswered_questions(request):
    def filter_unanswered_questions(user_id: int, begin: int, end: int = None, count: int = False,
                                    order_by: dict = None, kfilter: dict = None):
        if not isinstance(kfilter, dict):
            kfilter = {}
        kexclude = {'answer__user_id': user_id}
        if get_user_model().objects.filter(id=user_id).exclude(role='Admin'):
            kfilter['state'] = 'Approved'
        if count:
            return Question.objects.filter(**kfilter).exclude(**kexclude).count()
        elif isinstance(order_by, dict):
            kalias = order_by.get('kalias') or {}
            order_by = order_by.get('sorter') or []
            if end is not None:
                return Question.objects.filter(**kfilter).exclude(**kexclude).alias(**kalias).order_by(*order_by)[
                       begin:end]
            return Question.objects.filter(**kfilter).exclude(**kexclude).alias(**kalias).order_by(*order_by)[begin:]
        else:
            if end is not None:
                return Question.objects.filter(**kfilter).exclude(answer__user_id=user_id)[begin:end]
            return Question.objects.filter(**kfilter).exclude(answer__user_id=user_id)[begin:]

    return view_questions(request=request,
                          path_name='practice:view_unanswered_questions',
                          function_filter=filter_unanswered_questions)


@ensure_is_not_anonymous_user
def process_profile(request, profile_id):
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
        'code': {
            'label': _('Mã người dùng'),
            'value': '',
        },
        'back_url': '',
        'error': '',
        'readonly': False,
    }

    def valid_form_profile(_data):
        first_invalid = ''
        params = request.POST

        _data['code']['value'] = request.user.code

        email = params.get('email')
        if not email:
            first_invalid = 'email'
            _data['email']['errors'].append(_('Trường này không được để trống.'))
        else:
            _data['email']['value'] = email
            if len(email) > 255:
                first_invalid = 'email'
                _data['email']['errors'].append(_('Trường này không được nhập quá 255 ký tự.'))
            pattern = re.compile(
                r'^[^@\[\]<>(),:;.\s\\\"]+(\.[^@\[\]<>(),:;.\s\\\"]+)*@([^@\[\]<>(),:;.\s\\\"]+\.)+[^@\[\]<>(),:;.\s\\\"]{2,}$')
            if not re.match(pattern=pattern, string=email):
                first_invalid = 'email'
                _data['email']['errors'].append(_('Email không đúng định dạng.'))
            elif get_user_model().objects.filter(email=get_user_model().objects.normalize_email(email)).exclude(
                    id=request.user.id):
                first_invalid = 'email'
                _data['email']['errors'].append('Email đã được đăng ký với tài khoản khác.')

        name = params.get('name')
        if not name:
            first_invalid = 'name'
            _data['name']['errors'].append(_('Trường này không được để trống.'))
        else:
            _data['name']['value'] = name
            if len(name) > 255:
                first_invalid = 'name'
                _data['name']['errors'].append(_('Trường này không được nhập quá 255 ký tự.'))

        if first_invalid:
            _data['autofocus'] = first_invalid
            return _data, False
        else:
            return _data, True

    notification = ''
    if request.method == 'POST':
        if profile_id != request.user.id:
            return HttpResponseBadRequest()

        data, is_valid = valid_form_profile(_data=data)
        if is_valid:
            user = get_user_model().objects.filter(id=request.user.id)
            if user:
                has_changed = False
                if user[0].name != data['name']['value']:
                    user[0].name = data['name']['value']
                    has_changed = True
                normalize_email = get_user_model().objects.normalize_email(data['email']['value'])
                if user[0].email != normalize_email:
                    user[0].email = normalize_email
                    has_changed = True
                if has_changed:
                    user[0].save()
            notification = 'Sửa thông tin thành công'

        if request.session.get('post_profile_back_url'):
            data['back_url'] = urlsafe_base64_decode(request.session['post_profile_back_url']).decode('utf-8')

    elif request.method == 'GET':
        if profile_id == request.user.id:
            data['name']['value'] = request.user.name
            data['email']['value'] = request.user.email
            data['code']['value'] = request.user.code
        else:
            profile = get_user_model().objects.filter(id=profile_id)
            if profile:
                data['name']['value'] = profile[0].name
                data['email']['value'] = profile[0].email
                data['code']['value'] = profile[0].code
                data['readonly'] = True
            else:
                return HttpResponseBadRequest()

        if request.META['HTTP_REFERER']:
            if request.META['HTTP_REFERER'] != request.build_absolute_uri():
                request.session['post_profile_back_url'] = urlsafe_base64_encode(
                    request.META['HTTP_REFERER'].encode('utf-8'))

            if request.session.get('post_profile_back_url'):
                data['back_url'] = urlsafe_base64_decode(request.session['post_profile_back_url']).decode('utf-8')

    return render(request,
                  template_name='practice/profile.html',
                  context={'data': data, 'notification': notification})


@ensure_is_not_anonymous_user
def process_new_question(request):
    data = {
        'tag_id': {
            'label': _('Nhãn câu hỏi'),
            'value': 0,
            'errors': [],
        },
        'title': {
            'label': _('Tiêu đề'),
            'value': '',
            'errors': [],
        },
        'choices': {
            'label': _('Các lựa chọn (tối thiểu phải có 2 lựa chọn có nội dung)'),
            'values': ['', '', '', ''],
            'errors': [],
        },
        'true_choice': {
            'label': _('Lựa chọn đúng (phải có 1 lựa chọn có nội dung là lựa chọn đúng)'),
            'value': 0,
            'errors': [],
        },
        'image': {
            'label': _('Hình ảnh (tệp *.png, *.jpg hoặc *.jpeg và kích thước dưới 2MB)'),
            'value': '',
            'errors': [],
        },
        'autofocus': 'title',
        'back_url': '',
    }

    def valid_form_new_question(_data):
        first_invalid = ''

        image = request.FILES.get('image') or None
        if image:
            limit_image_file_size = 2097152  # 2 * 1024 * 1024
            if image.content_type not in ('image/png', 'image/jpeg'):
                first_invalid = 'image'
                _data['image']['errors'].append(_('Hình ảnh phải là ảnh .png, .jpg hoặc .jpeg'))
            if image.size >= limit_image_file_size:
                first_invalid = 'image'
                _data['image']['errors'].append(_('Kích thước hình ảnh phải bé hơn 2MB'))
            else:
                _data['image']['value'] = image

        params = request.POST

        choices = []
        choice_order = 1
        while f'choice_{choice_order}' in params:
            choices.append(params.get(f'choice_{choice_order}') or '')
            choice_order += 1
        while choice_order <= 4:
            choices.append('')
            choice_order += 1

        if len(choices) - choices.count('') < 2:
            first_invalid = 'choices'
            _data['choices']['errors'].append(_('Phải có ít nhất 2 lựa chọn có nội dung.'))

        _data['choices']['values'] = choices

        true_choice = params.get('true_choice')
        if not true_choice:
            first_invalid = 'choices'
            _data['choices']['errors'].append(_('Phải có 1 lựa chọn đúng.'))
        else:
            true_choice = convert_to_non_negative_int(true_choice)
            _data['true_choice']['value'] = true_choice
            if first_invalid != 'choices':
                if true_choice < 1:
                    first_invalid = 'choices'
                    _data['choices']['errors'].append(_('Phải có 1 lựa chọn đúng.'))
                else:
                    if true_choice > len(choices) or not choices[true_choice - 1]:
                        first_invalid = 'choices'
                        _data['choices']['errors'].append(_('Lựa chọn đúng phải là 1 trong các lựa chọn có nội dung'))

        title = params.get('title') or ''
        if not title:
            first_invalid = 'title'
            _data['title']['errors'].append(_('Trường này không được để trống.'))
        else:
            _data['title']['value'] = title

        tag_id = params.get('tag_id') or ''
        if not tag_id:
            first_invalid = 'tag_id'
            _data['tag_id']['errors'].append(_('Trường này không được để trống.'))
        else:
            tag_id = convert_to_non_negative_int(tag_id)
            _data['tag_id']['value'] = tag_id
            if tag_id < 1:
                first_invalid = 'tag_id'
                _data['tag_id']['errors'].append(_('Trường này không được để trống.'))
            elif not QuestionTag.objects.filter(id=tag_id):
                first_invalid = 'tag_id'
                _data['tag_id']['errors'].append(_('Nhãn này không hợp lệ.'))

        if first_invalid:
            _data['autofocus'] = first_invalid
            return _data, False
        else:
            return _data, True

    if request.method == 'POST':
        data, is_valid = valid_form_new_question(_data=data)
        if is_valid:
            data['title']['value'] = data['title']['value'].strip()
            not_empty_choices = []
            true_choice0 = data['true_choice']['value'] - 1
            j = 1
            for i, choice in enumerate(data['choices']['values']):
                if true_choice0 == i:
                    data['true_choice']['value'] = j
                if choice:
                    j += 1
                    not_empty_choices.append(choice.strip())
            data['choices']['values'] = not_empty_choices

            q = Question(title=data['title']['value'],
                         state='Pending',
                         choices=data['choices']['values'],
                         true_choice=data['true_choice']['value'],
                         tag_id=data['tag_id']['value'],
                         user_id=request.user.id,
                         image=data['image']['value'],
                         created_at=datetime.datetime.now(datetime.timezone.utc))
            q.save()

            return redirect(f'{reverse("practice:view_created_questions")}?notification=create_question_success')

    return render(request,
                  "practice/new_question.html",
                  context={
                      'data': data,
                      'tags': QuestionTag.objects.all(),
                      "logout_link": reverse('users:logout'),
                      "change_password_link": reverse('users:change_password'),
                  })


@ensure_is_not_anonymous_user
def process_new_answer(request, question_id):
    data = {
        'choice': {
            'label': _('Lựa chọn'),
            'value': 0,
            'errors': [],
        },
        'back_url': '',
    }

    def valid_form_new_answer(_data, choices):
        first_invalid = ''
        params = request.POST

        choice = params.get('choice')
        if not choice:
            first_invalid = 'choice'
            _data['choice']['errors'].append(_('Phải chọn 1 lựa chọn.'))
        else:
            choice = convert_to_non_negative_int(choice)
            _data['choice']['value'] = choice
            if choice > len(choices) or choice < 1:
                first_invalid = 'choice'
                _data['choice']['errors'].append(_('Phải chọn 1 lựa chọn trong các lựa chọn.'))

        return _data, not first_invalid

    question = Question.objects.filter(id=question_id,state='Approved')
    if not question:
        return HttpResponseNotFound()
    question = question[0]
    if request.method == 'POST':
        data, is_valid = valid_form_new_answer(_data=data, choices=question.choices)
        if is_valid:
            a = Answer(
                choice=data['choice']['value'],
                question_id=question_id,
                user_id=request.user.id,
                created_at=datetime.datetime.now(datetime.timezone.utc),
            )
            a.save()
            return redirect(
                f'{reverse("practice:view_detail_question", args=[question_id])}?notification=create_answer_success')

    return render(request,
                  "practice/new_answer.html",
                  context={
                      'data': data,
                      'question': question,
                      "logout_link": reverse('users:logout'),
                      "change_password_link": reverse('users:change_password'),
                  })


@ensure_is_not_anonymous_user
def view_detail_question(request, question_id):
    if request.user.role == 'Admin':
        question = get_object_or_404(Question, pk=question_id)
    else:
        question = Question.objects.filter(state='Approved') or Question.objects.filter(user_id=request.user.id)
        if not question:
            return HttpResponseNotFound()
        question = question[0]
    notification = ''
    past_answers = []
    if request.method == 'GET':
        notification = request.GET.get('notification') or ''
        if notification == 'create_answer_success':
            notification = 'Tạo câu trả lời thành công'
        elif notification == 'approved_success':
            notification = 'Thực hiện duyệt câu hỏi thành công'
        elif notification == 'unapproved_success':
            notification = 'Thực hiện không duyệt câu hỏi thành công'
        elif notification == 'locked_success':
            notification = 'Thực hiện khóa câu hỏi thành công'
        past_answers = Answer.objects.filter(user_id=request.user.id,question_id=question_id)
    return render(request,
                  "practice/detail_question.html",
                  {
                      "question": question,
                      'notification': notification,
                      'past_answers': past_answers,
                      "logout_link": reverse('users:logout'),
                      "change_password_link": reverse('users:change_password'),
                  })


@ensure_is_not_anonymous_user
def view_detail_answer(request, answer_id=None):
    if request.user.role != 'Admin':
        answer = get_object_or_404(Answer, pk=answer_id)
    else:
        answer = Answer.objects.filter(user_id=request.user.id,question__state='Approved') or Question.objects.filter(user_id=request.user.id,question__user_id=request.user.id)
        if not answer:
            return HttpResponseNotFound()
        answer = answer[0]
    return render(request,
                  "practice/detail_answer.html",
                  {
                      "answer": answer,
                      "logout_link": reverse('users:logout'),
                      "change_password_link": reverse('users:change_password'),
                  })


def get_comments(question, params, data):
    limit = convert_to_non_negative_int(string=(params.get('limit') or ''), default=4) or 4
    page_count = math_ceil(question.comment_set.count() / limit) or 1
    page_offset = convert_to_int(string=(params.get('offset') or ''), default=1)
    if page_offset > 1:
        page_offset = page_offset if page_offset < page_count else page_count
    else:
        page_offset = page_count if page_offset == -1 else 1
    offset = (page_offset - 1) * limit
    comments = question.comment_set.filter(state='Normal').order_by('-created_at')[offset:(offset + limit)]
    return {
        "showing_comments": True,
        "question": question,
        "comments": comments,
        "comment_page_range": range(1, page_count + 1),
        "comment_conditions": {
            "page_offset": page_offset,
            "limit": limit,
        },
        "suffix_utc": '' if not timezone.get_current_timezone_name() == 'UTC' else 'UTC',
        "logout_link": reverse('users:logout'),
        "change_password_link": reverse('users:change_password'),
        "data": data,
    }


def create_new_comment(question, request):
    comment_content = (request.POST.get('comment_content') or '').strip()
    if comment_content:
        c = Comment(
            content=comment_content,
            question_id=question.id,
            user_id=request.user.id,
            created_at=datetime.datetime.now(datetime.timezone.utc)
        )

        c.save()

        return '1'
    return request.POST.get('offset') or ''


@ensure_is_not_anonymous_user
def process_comments_in_question(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    data = {
        'comment_content': {
            'label': _('Bình luận mới'),
            'value': '',
            'errors': [],
        },
        'error': '',
    }
    if request.method == 'GET':
        context = get_comments(question, request.GET, data)
        return render(request, "practice/detail_question.html", context)
    elif request.method == 'POST':
        offset = create_new_comment(question, request)
        to_method_get_url = f'{reverse("practice:process_comments_in_question", args=[question_id])}?limit={request.POST.get("limit") or ""}&offset={offset}'
        return redirect(to=to_method_get_url)


@ensure_is_not_anonymous_user
def process_comments_in_answer(request, answer_id):
    answer = get_object_or_404(Answer, pk=answer_id)
    data = {
        'comment_content': {
            'label': _('Bình luận mới'),
            'value': '',
            'errors': [],
        },
        'error': '',
    }
    question = answer.question
    if request.method == 'GET':
        context = get_comments(question, request.GET, data)
        context["answer"] = answer
        return render(request, "practice/detail_answer.html", context)
    elif request.method == 'POST':
        context = create_new_comment(question, request, data)
        context["answer"] = answer
        return render(request, "practice/detail_answer.html", context)


def process_new_question_evaluation(request):
    data = {
        'evaluation_content': {
            'label': _('Đánh giá mới'),
            'value': '',
            'errors': [],
        },
        'comment_content': {
            'label': _('Bình luận mới'),
            'value': '',
            'errors': [],
        },
        'error': '',
    }
    showing_evaluation = True
    notification = ''
    if request.method == 'GET':
        params = request.GET
        qid = convert_to_non_negative_int(string=params.get('qid'))
        question = Question.objects.filter(id=qid,state='Approved')
        if not question:
            return HttpResponseNotFound()
        question = question[0]
    else:
        params = request.POST
        qid = convert_to_non_negative_int(string=params.get('qid'))
        question = Question.objects.filter(id=qid, state='Approved')
        if not question:
            return HttpResponseNotFound()
        question = question[0]
        evaluation_content = (request.POST.get('evaluation_content') or '').strip()
        if evaluation_content:
            qe = QuestionEvaluation(
                content=evaluation_content,
                comment_id=question.id,
                user_id=request.user.id,
                created_at=datetime.datetime.now(datetime.timezone.utc)
            )

            qe.save()
            notification = 'Tạo đánh giá thành công'
            showing_evaluation = False
        else:
            data['evaluation_content']['value'] = evaluation_content
    if params.get('coffset') and params.get('climit'):
        context = get_comments(question, {'offset': params.get('coffset'), 'limit': params.get('climit')}, data)
    else:
        context = {
            "suffix_utc": '' if not timezone.get_current_timezone_name() == 'UTC' else 'UTC',
            "logout_link": reverse('users:logout'),
            "change_password_link": reverse('users:change_password'),
            "question": question,
            "data": data,
        }
    context["showing_evaluation"] = showing_evaluation
    context["notification"] = notification
    return render(request, "practice/detail_question.html", context)


def process_new_comment_evaluation(request):
    data = {
        'evaluation_content': {
            'label': _('Đánh giá mới'),
            'value': '',
            'errors': [],
        },
        'error': '',
    }
    notification = ''
    if request.method == 'GET':
        params = request.GET
        cid = convert_to_non_negative_int(string=params.get('cid'))
        comment = Question.objects.filter(id=cid, state='Normal')
        if not comment:
            return HttpResponseNotFound()
        comment = comment[0]
    else:
        params = request.POST
        cid = convert_to_non_negative_int(string=params.get('cid'))
        comment = Question.objects.filter(id=cid, state='Normal')
        if not comment:
            return HttpResponseNotFound()
        comment = comment[0]
        evaluation_content = (request.POST.get('evaluation_content') or '').strip()
        if evaluation_content:
            ce = CommentEvaluation(
                content=evaluation_content,
                comment_id=comment.id,
                user_id=request.user.id,
                created_at=datetime.datetime.now(datetime.timezone.utc)
            )

            ce.save()
            notification = 'Tạo đánh giá thành công'
    context = {
        'comment': comment,
        'notification': notification,
        'data': data,
    }
    return render(request, "practice/new_comment_evaluation.html", context)


@ensure_is_not_anonymous_user
def process_new_evaluation(request):
    if request.method == 'GET':
        params = request.GET
    elif request.method == 'POST':
        params = request.POST
    else:
        return HttpResponseBadRequest()

    if 'qid' in params:
        return process_new_question_evaluation(request)
    elif 'cid' in params:
        return process_new_comment_evaluation(request)
    else:
        return HttpResponseBadRequest()


# ========================================== Admin ====================================================
@ensure_is_admin
def process_detail_question_by_admin(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    notification = ''
    if request.method == 'POST':
        params = request.POST
        # 1 : Pending -> Approved
        # 2 : Pending -> Unapproved
        # 3 : Approved -> Locked
        action = convert_to_non_negative_int(string=(params.get('action')))
        if action == 1:
            if question.state == 'Pending':
                question.state = 'Approved'
                question.save()
                lg = Log(
                    model_name='Question',
                    object_id=question_id,
                    user_id=request.user.id,
                    content="Pending -> Approved",
                    created_at=datetime.datetime.now(datetime.timezone.utc)
                )

                lg.save()
                notification = 'approved_success'
        elif action == 2:
            if question.state == 'Pending':
                question.state = 'Unapproved'
                question.save()

                lg = Log(
                    model_name='Question',
                    object_id=question_id,
                    user_id=request.user.id,
                    content="Pending -> Unapproved",
                    created_at=datetime.datetime.now(datetime.timezone.utc)
                )

                lg.save()

                notification = 'unapproved_success'
        elif action == 3:
            if question.state == 'Approved':
                question.state = 'Locked'
                question.save()

                lg = Log(
                    model_name='Question',
                    object_id=question_id,
                    user_id=request.user.id,
                    content="Approved -> Locked",
                    created_at=datetime.datetime.now(datetime.timezone.utc)
                )

                lg.save()

                notification = 'locked_success'
        else:
            return HttpResponseBadRequest()
        return redirect(to=f'{reverse("practice:view_detail_question", args=[question_id])}?notification={notification}')


@ensure_is_admin
def view_pending_questions_by_admin(request):
    pass


@ensure_is_admin
def view_locked_questions_by_admin(request):
    pass


@ensure_is_admin
def view_unapproved_questions_by_admin(request):
    pass


@ensure_is_admin
def view_approved_questions_by_admin(request):
    pass


@ensure_is_admin
def view_evaluations_by_admin(request):
    pass


@ensure_is_admin
def process_evaluation_by_admin(request, evaluation_id):
    pass
