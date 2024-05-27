import datetime
from math import ceil as math_ceil
import re

from django.contrib.sessions.models import Session
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


def get_page_offset(offset_in_params: str, page_count: int):
    page_offset = convert_to_int(string=offset_in_params, default=1)
    if page_offset > 1:
        page_offset = page_offset if page_offset < page_count else page_count
    else:
        page_offset = page_count if page_offset == -1 else 1
    return page_offset


def view_questions(request, path_name=None, kfilter=None, kexclude=None, notification=''):
    filters_and_sorters_key_name = f'{path_name}__filters_and_sorters'
    limit_of_lists_key_name = 'practice.views.view_questions__limit'
    params = request.GET

    order_by = []
    kalias = {}
    kexclude = kexclude or {}
    kfilter = kfilter or {}

    tag_id = convert_to_int(string=params.get('tid', ''), default=0)
    tags = QuestionTag.objects.all()
    if request.user.role != 'Admin':
        if tags:
            if tag_id <= 0 or not tags.filter(id=tag_id):
                tag_id = tags[0].id
            kfilter['tag_id'] = tag_id
        else:
            raise Http404()
    elif tag_id != -1:
        if tag_id <= 0 or not tags.filter(id=tag_id):
            tag_id = -1
        else:
            kfilter['tag_id'] = tag_id

    limit = convert_to_non_negative_int(string=params.get('limit', ''), default=0)
    if not limit:
        limit = request.session.get(limit_of_lists_key_name, 4)
    elif limit != request.session.get(limit_of_lists_key_name, 0):
        request.session[limit_of_lists_key_name] = limit

    if (params.get('filter') or '') == 'input':
        request.session[filters_and_sorters_key_name] = {
            'filter_by_created_at_from': params.get('filter_by_created_at_from'),
            'filter_by_created_at_to': params.get('filter_by_created_at_to'),
            'filter_by_content': params.get('filter_by_content'),
            'filter_by_hashtag': params.get('filter_by_hashtag'),
            'filter_by_author_name': params.get('filter_by_author_name'),
            'filter_by_author_code': params.get('filter_by_author_code'),
            'sorter_with_created_at': params.get('sorter_with_created_at'),
            'sorter_with_decreasing_number_of_answers': params.get('sorter_with_decreasing_number_of_answers'),
            'sorter_with_decreasing_number_of_comments': params.get('sorter_with_decreasing_number_of_comments'),
        }
    elif not request.session.get(filters_and_sorters_key_name):
        request.session[filters_and_sorters_key_name] = {
            'filter_by_created_at_from': '',
            'filter_by_created_at_to': '',
            'filter_by_content': '',
            'filter_by_hashtag': '',
            'filter_by_author_name': '',
            'filter_by_author_code': '',
            'sorter_with_created_at': '',
            'sorter_with_decreasing_number_of_answers': False,
            'sorter_with_decreasing_number_of_comments': False,
        }

    _filters_and_sorters = request.session[filters_and_sorters_key_name]

    created_at_from = _filters_and_sorters['filter_by_created_at_from']
    if created_at_from:
        kfilter['created_at__gte'] = datetime.datetime.strptime(created_at_from + ':00.000000', '%Y-%m-%dT%H:%M:%S.%f')
    created_at_to = _filters_and_sorters['filter_by_created_at_to']
    if created_at_to:
        kfilter['created_at__lte'] = datetime.datetime.strptime(created_at_to + ':59.999999', '%Y-%m-%dT%H:%M:%S.%f')

    contents = _filters_and_sorters['filter_by_content']
    if contents:
        contents = [content.strip() for content in contents.split(',') if content.strip()]
        if contents:
            kfilter['content__iregex'] = r"^.*" + ('|'.join(contents)) + r".*$"

    hashtags = _filters_and_sorters['filter_by_hashtag']
    if hashtags:
        hashtags = [hashtag.strip() for hashtag in hashtags.split(',') if hashtag.strip()]
        if hashtags:
            kfilter['hashtags__iregex'] = r"^.*" + ('|'.join(hashtags)) + r".*$"

    author_names = _filters_and_sorters['filter_by_author_name']
    if author_names:
        author_names = [author_name.strip() for author_name in author_names.split(',') if author_name.strip()]
        if author_names:
            kfilter['user__name__iregex'] = r"^.*" + ('|'.join(author_names)) + r".*$"

    author_codes = _filters_and_sorters['filter_by_author_code']
    if author_codes:
        author_codes = [author_code.strip() for author_code in author_codes.split(',') if author_code.strip()]
        if author_codes:
            kfilter['user__code__iregex'] = r"^.*" + ('|'.join(author_codes)) + r".*$"

    if _filters_and_sorters['sorter_with_decreasing_number_of_comments']:
        kalias['comment__count'] = Count('comment')
        order_by.append('-comment__count')

    if _filters_and_sorters['sorter_with_decreasing_number_of_answers']:
        kalias['answer__count'] = Count('answer')
        order_by.append('-answer__count')

    order_by.append('created_at' if _filters_and_sorters['sorter_with_created_at'] == '+' else '-created_at')

    page_count = math_ceil(Question.objects.filter(**kfilter).exclude(**kexclude).distinct().count() / limit) or 1

    page_offset = convert_to_int(string=params.get('offset', ''), default=1)
    if page_offset > 1:
        page_offset = page_offset if page_offset < page_count else page_count
    else:
        page_offset = page_count if page_offset == -1 else 1
    offset = (page_offset - 1) * limit

    original_questions = Question.objects.filter(**kfilter).exclude(**kexclude).alias(**kalias).order_by(*order_by).distinct()[offset:(offset + limit)]
    questions = []
    for question in original_questions:
        question.__setattr__('number_of_answers', question.answer_set.count())
        question.__setattr__('number_of_comments', question.comment_set.count())
        questions.append(question)

    context = {
        "notification": notification,
        "suffix_utc": '' if not timezone.get_current_timezone_name() == 'UTC' else 'UTC',
        "questions": questions,
        "tags": tags,
        "question_conditions": {
            "page_range": range(1, page_count + 1),
            "limits": [4, 8, 16],
            "path_name": path_name,
            "tag_id": tag_id,
            "limit": limit,
            "include_limit_exclude_offset_url": f"{reverse(path_name)}?tid={tag_id}&limit={limit}",
            "page_offset": page_offset,
            'filter_by_created_at_from': _filters_and_sorters.get('filter_by_created_at_from'),
            'filter_by_created_at_to': _filters_and_sorters.get('filter_by_created_at_to'),
            'filter_by_content': _filters_and_sorters.get('filter_by_content'),
            'filter_by_hashtag': _filters_and_sorters.get('filter_by_hashtag'),
            'filter_by_author_name': _filters_and_sorters.get('filter_by_author_name'),
            'filter_by_author_code': _filters_and_sorters.get('filter_by_author_code'),
            'sorter_with_created_at': _filters_and_sorters.get('sorter_with_created_at'),
            'sorter_with_decreasing_number_of_answers': _filters_and_sorters.get('sorter_with_decreasing_number_of_answers'),
            'sorter_with_decreasing_number_of_comments': _filters_and_sorters.get('sorter_with_decreasing_number_of_comments'),
        },
    }

    return render(request, template_name='practice/questions.html', context=context)


notification_to_view_created_questions_key_name = 'practice.views.view_created_questions__notification'
notification_to_process_new_question_key_name = 'practice.views.process_new_question__notification'
notification_to_view_detail_question_key_name = 'practice.views.view_detail_question__notification'
notification_to_process_profile_key_name = 'practice.views.process_profile___notification'


@ensure_is_not_anonymous_user
def view_created_questions(request):
    notification = ''
    if request.method == 'GET':
        notification = request.session.get(notification_to_view_created_questions_key_name, '')
        request.session[notification_to_view_created_questions_key_name] = ''

    return view_questions(request=request, path_name='practice:view_created_questions', kfilter={'user_id': request.user.id}, notification=notification)


@ensure_is_not_anonymous_user
def view_answered_questions(request):
    return view_questions(request=request, path_name='practice:view_answered_questions', kfilter={'answer__user_id': request.user.id, 'state': 'Approved'})


@ensure_is_not_anonymous_user
def view_unanswered_questions(request):
    return view_questions(request=request, path_name='practice:view_unanswered_questions', kfilter={'state': 'Approved'}, kexclude={'answer__user_id': request.user.id})


@ensure_is_not_anonymous_user
def view_root(request):
    if request.user.role != 'Admin':
        return redirect("practice:view_unanswered_questions")
    else:
        return redirect("practice:view_pending_questions_by_admin")


@ensure_is_not_anonymous_user
def process_profile(request, profile_id):
    prev_adj_url_key_name = 'practice.views.process_profile__previous_adjacent_url'
    data = {
        'name':  {'errors': [], 'value': '', 'label': _('Họ và tên')    },
        'email': {'errors': [], 'value': '', 'label': _('Email')        },
        'code': {               'value': '', 'label': _('Mã người dùng')},
        'errors': [],
        'previous_adjacent_url': '',
        'readonly': False,
    }
    notification = ''

    profile = get_object_or_404(get_user_model(), pk=profile_id)

    if request.method == 'POST':
        if profile_id != request.user.id:
            return HttpResponseBadRequest()

        is_valid = True
        params = request.POST

        data['code']['value'] = request.user.code

        email = params.get('email')
        if not email:
            is_valid = False
            data['email']['errors'].append(_('Trường này không được để trống.'))
        else:
            data['email']['value'] = email
            if len(email) > 255:
                is_valid = False
                data['email']['errors'].append(_('Trường này không được nhập quá 255 ký tự.'))
            pattern = re.compile(
                r'^[^@\[\]<>(),:;.\s\\\"]+(\.[^@\[\]<>(),:;.\s\\\"]+)*@([^@\[\]<>(),:;.\s\\\"]+\.)+[^@\[\]<>(),:;.\s\\\"]{2,}$')
            if not re.match(pattern=pattern, string=email):
                is_valid = False
                data['email']['errors'].append(_('Email không đúng định dạng.'))
            elif get_user_model().objects.filter(email=get_user_model().objects.normalize_email(email)).exclude(
                    id=request.user.id):
                is_valid = False
                data['email']['errors'].append('Email đã được đăng ký với tài khoản khác.')

        name = params.get('name')
        if not name:
            is_valid = False
            data['name']['errors'].append(_('Trường này không được để trống.'))
        else:
            data['name']['value'] = name
            if len(name) > 255:
                is_valid = False
                data['name']['errors'].append(_('Trường này không được nhập quá 255 ký tự.'))

        if is_valid:
            has_changed = False
            if request.user.name != data['name']['value']:
                request.user.name = data['name']['value']
                has_changed = True
            normalize_email = get_user_model().objects.normalize_email(data['email']['value'])
            if request.user.email != normalize_email:
                request.user.email = normalize_email
                has_changed = True
            if has_changed:
                request.user.save()

            notification = 'Sửa thông tin thành công'

        if request.session.get(prev_adj_url_key_name):
            data['previous_adjacent_url'] = urlsafe_base64_decode(request.session[prev_adj_url_key_name]).decode('utf-8')

    elif request.method == 'GET':
        if profile_id == request.user.id:
            data['name']['value'] = request.user.name
            data['email']['value'] = request.user.email
            data['code']['value'] = request.user.code
        else:
            data['name']['value'] = profile.name
            data['email']['value'] = profile.email
            data['code']['value'] = profile.code
            data['readonly'] = True

        request_url = request.build_absolute_uri()
        referer_url = request.META['HTTP_REFERER']
        if referer_url and request_url != referer_url:
            request.session[prev_adj_url_key_name] = urlsafe_base64_encode(
                request.META['HTTP_REFERER'].encode('utf-8'))

        if request.session.get(prev_adj_url_key_name):
            data['previous_adjacent_url'] = urlsafe_base64_decode(request.session[prev_adj_url_key_name]).decode('utf-8')

        notification = request.session.get(notification_to_process_profile_key_name, '')
        request.session[notification_to_process_profile_key_name] = ''

    context = {
        "suffix_utc": '' if not timezone.get_current_timezone_name() == 'UTC' else 'UTC',
        'notification': notification,
        'profile_id': profile_id,
        'profile_locked': profile.state == 'Locked',
        'profile_role': profile.role,
        'data': data,
    }
    return render(request, template_name='practice/profile.html', context=context)


@ensure_is_not_anonymous_user
def process_new_question(request):
    default_choice = {'content': '', 'is_true': False}
    data = {
        'tag_id':   {'errors': [], 'value': 0 , 'label': _('Nhãn câu hỏi')},
        'hashtags': {'errors': [], 'value': [], 'label': _('Các hashtag')},
        'content':  {'errors': [], 'value': '', 'label': _('Nội dung câu hỏi')},
        'choices':  {'errors': [], 'value': [default_choice, default_choice, default_choice, default_choice], 'label': _('Các lựa chọn (tối thiểu phải có 2 lựa chọn có nội dung, có ít nhất 1 lựa chọn có nội dung là lựa chọn đúng))')},
        'image':    {'errors': [], 'value': '', 'label': _('Hình ảnh (1 tệp *.png, *.jpg hoặc *.jpeg và kích thước dưới 2MB)')},
        'errors': [],
        'previous_adjacent_url': '',
    }

    if request.method == 'GET':
        referer_url = request.META['HTTP_REFERER']
        s = reverse('practice:view_created_questions')
        if referer_url and referer_url.startswith(request.build_absolute_uri(reverse('practice:view_created_questions'))):
            pattern = re.compile(r'\?tid=[0-9]+')
            match = re.search(pattern=pattern, string=referer_url)
            if match:
                s = match.string[match.regs[0][0] + len('?tid='): match.regs[0][1]]
                data['tag_id']['value'] = convert_to_non_negative_int(s)

    elif request.method == 'POST':
        is_valid = True

        image = request.FILES.get('image')
        if image:
            limit_image_file_size = 2097152  # 2 * 1024 * 1024
            if image.content_type not in ('image/png', 'image/jpeg'):
                is_valid = False
                data['image']['errors'].append(_('Hình ảnh phải là ảnh .png, .jpg hoặc .jpeg'))
                if image.size >= limit_image_file_size:
                    data['image']['errors'].append(_('Kích thước hình ảnh phải bé hơn 2MB'))
            elif image.size >= limit_image_file_size:
                is_valid = False
                data['image']['errors'].append(_('Kích thước hình ảnh phải bé hơn 2MB'))
            else:
                data['image']['value'] = image

        params = request.POST

        choices = []
        choice_order = 1
        choice_content_count = 0
        true_choice_count = 0
        valid_true_choice_count = 0
        while f'choice_content_{choice_order}' in params:
            choice_content = params.get(f'choice_content_{choice_order}', '')
            choice_is_true = params.get(f'choice_is_true_{choice_order}', False)
            choices.append({"content": choice_content, "is_true": choice_is_true})
            if choice_is_true:
                true_choice_count += 1
            if choice_content:
                choice_content_count += 1
                if choice_is_true:
                    valid_true_choice_count += 1
            choice_order += 1
        while choice_order <= 4:
            choices.append({"content": "", "is_true": False})
            choice_order += 1
        if choice_content_count < 2:
            is_valid = False
            data['choices']['errors'].append(_('Phải có ít nhất 2 lựa chọn có nội dung.'))
        if true_choice_count < 1:
            is_valid = False
            data['choices']['errors'].append(_('Phải có ít nhất 1 lựa chọn đúng.'))
        elif valid_true_choice_count == 0:
            is_valid = False
            data['choices']['errors'].append(_('Lựa chọn đúng phải là 1 trong các lựa chọn có nội dung'))
        data['choices']['value'] = choices

        content = params.get('content', '')
        if not content:
            is_valid = False
            data['content']['errors'].append(_('Trường này không được để trống.'))
        else:
            data['content']['value'] = content

        hashtags = params.get('hashtags', '')
        if hashtags:
            hashtags = hashtags.split(',')
            data['hashtags']['value'] = hashtags

        tag_id = params.get('tag_id', '')
        if not tag_id:
            is_valid = False
            data['tag_id']['errors'].append(_('Trường này không được để trống.'))
        else:
            tag_id = convert_to_non_negative_int(string=tag_id)
            data['tag_id']['value'] = tag_id
            if tag_id < 1:
                is_valid = False
                data['tag_id']['errors'].append(_('Trường này không được để trống.'))
            elif not QuestionTag.objects.filter(id=tag_id):
                is_valid = False
                data['tag_id']['errors'].append(_('Nhãn này không hợp lệ.'))

        if is_valid:
            hashtags = set()
            for hashtag in data['hashtags']['value']:
                hashtag = hashtag.strip()
                if hashtag:
                    hashtags.add(hashtag)
            data['hashtags']['value'] = list(hashtags)

            q = Question(content=data['content']['value'].strip(),
                         state='Pending',
                         choices=[choice for choice in data['choices']['value'] if choice['content']],
                         tag_id=data['tag_id']['value'],
                         user_id=request.user.id,
                         image=data['image']['value'],
                         hashtags=','.join(data['hashtags']['value']),
                         created_at=datetime.datetime.now(datetime.timezone.utc))
            q.save()

            request.session[notification_to_view_created_questions_key_name] = 'Tạo câu hỏi thành công'
            return redirect(to=f"{reverse('practice:view_created_questions')}?tid={data['tag_id']['value']}")

    return render(request, "practice/new_question.html", context={'data': data, 'tags': QuestionTag.objects.all()})


@ensure_is_not_anonymous_user
def process_new_answer(request, question_id):
    data = {
        'choices': {'value': [], 'errors': [], 'label': _('Lựa chọn')},
        'errors': [],
        'previous_adjacent_url': '',
    }

    question = Question.objects.filter(id=question_id, state='Approved')
    if not question:
        return HttpResponseNotFound()
    question = question[0]

    if request.method == 'POST':
        is_valid = True
        params = request.POST

        data['choices']['value'] = []
        if question.is_single_choice():
            choice = params.get('choice', '')
            if not choice:
                is_valid = False
                data['choices']['errors'].append(_('Phải chọn 1 lựa chọn.'))
            else:
                choice = convert_to_non_negative_int(string=choice)
                if 1 <= choice <= len(question.choices):
                    data['choices']['value'].append(choice)
                if not data['choices']['value']:
                    is_valid = False
                    data['choices']['errors'].append(_('Phải chọn 1 lựa chọn trong các lựa chọn.'))
        else:
            choices = []
            for choice_order in range(1, len(question.choices) + 1):
                choice = params.get(f'choice_{choice_order}')
                if choice:
                    choices.append(choice)
            if not choices:
                is_valid = False
                data['choices']['errors'].append(_('Phải chọn ít nhất 1 lựa chọn.'))
            else:
                for choice in choices:
                    choice = convert_to_non_negative_int(string=choice)
                    if 1 <= choice <= len(question.choices):
                        data['choices']['value'].append(choice)
                    if not data['choices']['value']:
                        is_valid = False
                        data['choices']['errors'].append(_('Phải chọn ít nhất 1 lựa chọn trong các lựa chọn.'))

        if is_valid:
            is_correct = True
            for i in data['choices']['value']:
                if not question.choices[i - 1]['is_true']:
                    is_correct = False
                    break
            if is_correct:
                for i in range(0, len(question.choices)):
                    if question.choices[i]['is_true'] and (i + 1) not in data['choices']['value']:
                        is_correct = False
                        break

            a = Answer(
                choices=data['choices']['value'],
                question_id=question_id,
                user_id=request.user.id,
                is_correct=is_correct,
                created_at=datetime.datetime.now(datetime.timezone.utc),
            )
            a.save()

            request.session[notification_to_view_detail_question_key_name] = 'Tạo câu trả lời thành công'
            return redirect(to="practice:view_detail_question", question_id=question_id)

    return render(request, "practice/new_answer.html", context={'data': data, 'question': question})


@ensure_is_not_anonymous_user
def view_detail_question(request, question_id):
    data = {
        'previous_adjacent_url': '',
    }
    notification = ''
    past_answers = []

    if request.user.role == 'Admin':
        question = get_object_or_404(Question, pk=question_id)
    else:
        question = Question.objects.filter(id=question_id, state='Approved') | Question.objects.filter(id=question_id, user_id=request.user.id)
        if not question:
            return HttpResponseNotFound()
        question = question[0]

    if request.method == 'GET':
        notification = request.session.get(notification_to_view_detail_question_key_name, '')
        request.session[notification_to_view_detail_question_key_name] = ''

        past_answers = Answer.objects.filter(user_id=request.user.id, question_id=question_id)

    context = {
        "suffix_utc": '' if not timezone.get_current_timezone_name() == 'UTC' else 'UTC',
        "question": question,
        "data": data, "notification": notification,
        "past_answers": past_answers,
    }
    return render(request, "practice/detail_question.html", context)


@ensure_is_not_anonymous_user
def view_detail_answer(request, answer_id=None):
    if request.user.role != 'Admin':
        answer = get_object_or_404(Answer, pk=answer_id)
    else:
        return HttpResponseBadRequest()

    context = {
        "suffix_utc": '' if not timezone.get_current_timezone_name() == 'UTC' else 'UTC',
        "answer": answer,
    }
    return render(request, "practice/detail_answer.html", context)


def get_comments_in_question(request, question, params, data):
    limit_of_lists_key_name = 'practice.views.get_comments_in_question__limit'

    limit = convert_to_non_negative_int(string=params.get('limit', ''), default=0)
    if not limit:
        limit = request.session.get(limit_of_lists_key_name, 4)
    elif limit != request.session.get(limit_of_lists_key_name, 0):
        request.session[limit_of_lists_key_name] = limit

    page_count = math_ceil(question.comment_set.count() / limit) or 1
    page_offset = convert_to_int(string=params.get('offset', ''), default=1)
    if page_offset > 1:
        page_offset = page_offset if page_offset < page_count else page_count
    else:
        page_offset = page_count if page_offset == -1 else 1
    offset = (page_offset - 1) * limit
    comments = question.comment_set.filter(state='Normal').order_by('-created_at')[offset:(offset + limit)]
    return {
        "suffix_utc": '' if not timezone.get_current_timezone_name() == 'UTC' else 'UTC',
        "showing_comments": True,
        "question": question,
        "comments": comments,
        "data": data,
        "comment_conditions": {
            "page_range": range(1, page_count + 1),
            "limits": [4, 8, 16],
            "page_offset": page_offset,
            "limit": limit,
            "include_limit_exclude_offset_url": f"{reverse('practice:process_comments_in_question', args=[question.id])}?limit={limit}",
        },
    }


@ensure_is_not_anonymous_user
def process_comments_in_question(request, question_id):
    question = Question.objects.filter(id=question_id, state='Approved')
    if not question:
        return HttpResponseNotFound()
    question = question[0]

    data = {
        'comment_content': {'errors': [], 'value': '', 'label': _('Bình luận mới')},
        'errors': [],
    }
    if request.method == 'GET':
        context = get_comments_in_question(request=request, question=question, params=request.GET, data=data)
    elif request.method == 'POST':
        is_valid = True
        params = dict(request.POST)
        data['comment_content']['value'] = params.get('comment_content', '')
        new_name = data['comment_content']['value'].strip()
        if not new_name:
            is_valid = False
            data['comment_content']['errors'].append(_('Bình luận phải có thể đọc.'))

        if is_valid:
            c = Comment(
                content=data['comment_content']['value'].strip(),
                question_id=question.id,
                user_id=request.user.id,
                created_at=datetime.datetime.now(datetime.timezone.utc)
            )
            c.save()
            params['offset'] = '1'

        context = get_comments_in_question(request=request, question=question, params=params, data=data)
    else:
        return HttpResponseBadRequest()

    return render(request, "practice/detail_question.html", context)


def process_new_question_evaluation(request, question):
    data = {
        'evaluation_content': {'errors': [], 'value': '', 'label': _('Đánh giá mới') },
        'comment_content':    {'errors': [], 'value': '', 'label': _('Bình luận mới')},
        'errors': [],
    }
    showing_evaluation = True
    notification = ''

    if request.method == 'GET':
        params = request.GET
    else:
        params = request.POST
        is_valid = True
        data['evaluation_content']['value'] = params.get('evaluation_content', '')
        new_name = data['evaluation_content']['value'].strip()
        if not new_name:
            is_valid = False
            data['evaluation_content']['errors'].append(_('Đánh giá phải có thể đọc.'))

        if is_valid:
            qe = QuestionEvaluation(
                content=data['evaluation_content']['value'].strip(),
                question_id=question.id,
                user_id=request.user.id,
                created_at=datetime.datetime.now(datetime.timezone.utc)
            )
            qe.save()
            notification = 'Tạo đánh giá thành công'
            showing_evaluation = False

    if params.get('coffset') and params.get('climit'):
        context = get_comments_in_question(request=request, question=question, params={'offset': params.get('coffset'), 'limit': params.get('climit')}, data=data)
    else:
        context = {
            "suffix_utc": '' if not timezone.get_current_timezone_name() == 'UTC' else 'UTC',
            "question": question,
            "data": data,
        }
    context["showing_evaluation"] = showing_evaluation
    context["notification"] = notification
    return render(request, "practice/detail_question.html", context)


def process_new_comment_evaluation(request, comment):
    data = {
        'evaluation_content': {'errors': [], 'value': '', 'label': _('Đánh giá mới')},
        'errors': [],
    }
    notification = ''

    if request.method == 'GET':
        params = request.GET
    else:
        params = request.POST
        is_valid = True
        data['evaluation_content']['value'] = params.get('evaluation_content', '')
        new_name = data['evaluation_content']['value'].strip()
        if not new_name:
            is_valid = False
            data['evaluation_content']['errors'].append(_('Đánh giá phải có thể đọc.'))

        if is_valid:
            ce = CommentEvaluation(
                content=data['evaluation_content']['value'].strip(),
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
        qid = convert_to_non_negative_int(string=params.get('qid', ''))
        question = Question.objects.filter(id=qid, state='Approved')
        if not question:
            return HttpResponseNotFound()
        question = question[0]

        return process_new_question_evaluation(request, question)
    elif 'cid' in params:
        cid = convert_to_non_negative_int(string=params.get('cid', ''))
        comment = Comment.objects.filter(id=cid, state='Normal')
        if not comment:
            return HttpResponseNotFound()
        comment = comment[0]

        return process_new_comment_evaluation(request, comment)
    else:
        return HttpResponseBadRequest()


# ========================================== Admin ====================================================
@ensure_is_admin
def process_detail_question_by_admin(request, question_id):
    question = get_object_or_404(Question, pk=question_id)

    if request.method != 'POST':
        return HttpResponseBadRequest()

    params = request.POST
    # 1 : Pending -> Approved
    # 2 : Pending -> Unapproved
    # 3 : Approved -> Locked
    # 4 : Locked -> Approved
    # 5 : Unapproved -> Approved
    action = convert_to_non_negative_int(string=params.get('action', ''))
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
            request.session[notification_to_view_detail_question_key_name] = 'Thực hiện duyệt câu hỏi thành công'
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
            request.session[notification_to_view_detail_question_key_name] = 'Thực hiện không duyệt câu hỏi thành công'
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
            request.session[notification_to_view_detail_question_key_name] = 'Thực hiện khóa câu hỏi thành công'
    elif action == 4:
        if question.state == 'Locked':
            question.state = 'Approved'
            question.save()
            lg = Log(
                model_name='Question',
                object_id=question_id,
                user_id=request.user.id,
                content="Locked -> Approved",
                created_at=datetime.datetime.now(datetime.timezone.utc)
            )
            lg.save()
            request.session[notification_to_view_detail_question_key_name] = 'Thực hiện mở khóa câu hỏi thành công'
    elif action == 5:
        if question.state == 'Unapproved':
            question.state = 'Approved'
            question.save()
            lg = Log(
                model_name='Question',
                object_id=question_id,
                user_id=request.user.id,
                content="Unapproved -> Approved",
                created_at=datetime.datetime.now(datetime.timezone.utc)
            )
            lg.save()
            request.session[notification_to_view_detail_question_key_name] = 'Thực hiện duyệt câu hỏi thành công'
    else:
        return HttpResponseBadRequest()

    return redirect(to="practice:view_detail_question", question_id=question_id)


@ensure_is_admin
def view_pending_questions_by_admin(request):
    return view_questions(request=request, path_name='practice:view_pending_questions_by_admin', kfilter={'state': 'Pending'})


@ensure_is_admin
def view_locked_questions_by_admin(request):
    return view_questions(request=request, path_name='practice:view_locked_questions_by_admin', kfilter={'state': 'Locked'})


@ensure_is_admin
def view_unapproved_questions_by_admin(request):
    return view_questions(request=request, path_name='practice:view_unapproved_questions_by_admin', kfilter={'state': 'Unapproved'})


@ensure_is_admin
def view_approved_questions_by_admin(request):
    return view_questions(request=request, path_name='practice:view_approved_questions_by_admin', kfilter={'state': 'Approved'})


def view_evaluations_by_admin(request, path_name=None, kfilter=None, kexclude=None):
    limit_of_lists_key_name = 'practice.views.view_evaluations_by_admin__limit'

    if request.method != 'GET':
        return HttpResponseBadRequest()

    params = request.GET

    evaluation_type = params.get('type', '')
    if evaluation_type != 'comment':
        evaluation_type = 'question'

    filters_and_sorters_key_name = f'{path_name}.{evaluation_type}__filters_and_sorters'

    if (params.get('filter') or '') == 'input':
        request.session[filters_and_sorters_key_name] = {
            'filter_by_content': params.get('filter_by_content', ''),
        }
    elif not request.session.get(filters_and_sorters_key_name):
        request.session[filters_and_sorters_key_name] = {
            'filter_by_content': '',
        }

    _filters_and_sorters = request.session[filters_and_sorters_key_name]
    filter_by_content = _filters_and_sorters['filter_by_content']

    limit = convert_to_non_negative_int(string=params.get('limit', ''), default=0)
    if not limit:
        limit = request.session.get(limit_of_lists_key_name, 4)
    elif limit != request.session.get(limit_of_lists_key_name, 0):
        request.session[limit_of_lists_key_name] = limit

    kexclude = kexclude or {}
    kfilter = kfilter or {}
    if filter_by_content:
        contents = [content.strip() for content in filter_by_content.split(',')]
        kfilter['content__iregex'] = r"^.*" + ('|'.join([content for content in contents if content])) + r".*$"

    if evaluation_type == 'comment':
        page_count = math_ceil(CommentEvaluation.objects.filter(**kfilter).exclude(**kexclude).count() / limit) or 1
    else:
        page_count = math_ceil(QuestionEvaluation.objects.filter(**kfilter).exclude(**kexclude).count() / limit) or 1

    page_offset = get_page_offset(offset_in_params=params.get('offset', ''), page_count=page_count)
    offset = (page_offset - 1) * limit

    if evaluation_type == 'comment':
        evaluations = CommentEvaluation.objects.filter(**kfilter).exclude(**kexclude).order_by('-id')[offset:(offset + limit)]
    else:
        evaluations = QuestionEvaluation.objects.filter(**kfilter).exclude(**kexclude).order_by('-id')[offset:(offset + limit)]

    context = {
        "suffix_utc": '' if not timezone.get_current_timezone_name() == 'UTC' else 'UTC',
        "evaluations": evaluations,
        "evaluation_conditions": {
            "type": evaluation_type,
            "page_range": range(1, page_count + 1),
            "limits": [4, 8, 16],
            "path_name": path_name,
            "limit": limit,
            "include_limit_exclude_offset_url": f"{reverse(path_name)}?type={evaluation_type}&limit={limit}",
            "page_offset": page_offset,
            'filter_by_content': filter_by_content,
        },
    }
    return render(request, "practice/evaluations.html", context)


@ensure_is_admin
def view_unlocked_evaluations_by_admin(request):
    return view_evaluations_by_admin(request=request, path_name='practice:view_unlocked_evaluations_by_admin', kexclude={'state': 'Locked'})


@ensure_is_admin
def view_locked_evaluations_by_admin(request):
    return view_evaluations_by_admin(request=request, path_name='practice:view_locked_evaluations_by_admin', kfilter={'state': 'Locked'})


@ensure_is_admin
def process_evaluation_by_admin(request, evaluation_id):
    data = {
        'previous_adjacent_url': '',
    }
    notification = ''

    if request.method == 'GET':
        params = request.GET
    elif request.method == 'POST':
        params = request.POST
    else:
        return HttpResponseBadRequest()

    evaluation_type = params.get('type', '')
    if evaluation_type != 'comment':
        evaluation_type = 'question'

    if evaluation_type != 'comment':
        evaluation = get_object_or_404(CommentEvaluation, pk=evaluation_id)
    else:
        evaluation = get_object_or_404(QuestionEvaluation, pk=evaluation_id)

    context = {
        "type": evaluation_type,
        "notification": notification,
        "evaluation": evaluation,
        "data": data,
    }
    return render(request, "practice/detail_comment.html", context)


def view_comments_by_admin(request, path_name=None, kfilter=None, kexclude=None):
    filters_and_sorters_key_name = f'{path_name}__filters_and_sorters'
    limit_of_lists_key_name = 'practice.views.view_comments_by_admin__limit'

    if request.method != 'GET':
        return HttpResponseBadRequest()

    params = request.GET

    if (params.get('filter') or '') == 'input':
        request.session[filters_and_sorters_key_name] = {
            'filter_by_content': params.get('filter_by_content', ''),
        }
    elif not request.session.get(filters_and_sorters_key_name):
        request.session[filters_and_sorters_key_name] = {
            'filter_by_content': '',
        }

    _filters_and_sorters = request.session[filters_and_sorters_key_name]
    filter_by_content = _filters_and_sorters['filter_by_content']

    limit = convert_to_non_negative_int(string=params.get('limit', ''), default=0)
    if not limit:
        limit = request.session.get(limit_of_lists_key_name, 4)
    elif limit != request.session.get(limit_of_lists_key_name, 0):
        request.session[limit_of_lists_key_name] = limit

    kexclude = kexclude or {}
    kfilter = kfilter or {}
    if filter_by_content:
        contents = [content.strip() for content in filter_by_content.split(',')]
        kfilter['content__iregex'] = r"^.*" + ('|'.join([content for content in contents if content])) + r".*$"

    page_count = math_ceil(Comment.objects.filter(**kfilter).exclude(**kexclude).count() / limit) or 1

    page_offset = get_page_offset(offset_in_params=params.get('offset', ''), page_count=page_count)
    offset = (page_offset - 1) * limit

    comments = Comment.objects.filter(**kfilter).exclude(**kexclude).order_by('-id')[offset:(offset + limit)]

    context = {
        "suffix_utc": '' if not timezone.get_current_timezone_name() == 'UTC' else 'UTC',
        "comments": comments,
        "comment_conditions": {
            "page_range": range(1, page_count + 1),
            "limits": [4, 8, 16],
            "path_name": path_name,
            "limit": limit,
            "include_limit_exclude_offset_url": f"{reverse(path_name)}?limit={limit}",
            "page_offset": page_offset,
            'filter_by_content': filter_by_content,
        },
    }
    return render(request, "practice/comments.html", context)


@ensure_is_admin
def view_unlocked_comments_by_admin(request):
    return view_comments_by_admin(request=request, path_name='practice:view_unlocked_comments_by_admin', kexclude={'state': 'Locked'})


@ensure_is_admin
def view_locked_comments_by_admin(request):
    return view_comments_by_admin(request=request, path_name='practice:view_locked_comments_by_admin', kfilter={'state': 'Locked'})


@ensure_is_admin
def process_comment_by_admin(request, comment_id):
    data = {
        'previous_adjacent_url': '',
    }
    notification = ''

    comment = get_object_or_404(Comment, pk=comment_id)

    context = {
        "notification": notification,
        "comment": comment,
        "data": data,
    }
    return render(request, "practice/detail_comment.html", context)


def view_users_by_admin(request, path_name=None, kfilter=None, kexclude=None):
    filters_and_sorters_key_name = f'{path_name}__filters_and_sorters'
    limit_of_lists_key_name = 'practice.views.view_users_by_admin__limit'

    if request.method != 'GET':
        return HttpResponseBadRequest()

    params = request.GET

    if (params.get('filter') or '') == 'input':
        request.session[filters_and_sorters_key_name] = {
            'filter_by_name': params.get('filter_by_name', ''),
        }
    elif not request.session.get(filters_and_sorters_key_name):
        request.session[filters_and_sorters_key_name] = {
            'filter_by_name': '',
        }

    _filters_and_sorters = request.session[filters_and_sorters_key_name]
    filter_by_name = _filters_and_sorters['filter_by_name']

    limit = convert_to_non_negative_int(string=params.get('limit', ''), default=0)
    if not limit:
        limit = request.session.get(limit_of_lists_key_name, 4)
    elif limit != request.session.get(limit_of_lists_key_name, 0):
        request.session[limit_of_lists_key_name] = limit

    kexclude = kexclude or {}
    kfilter = kfilter or {}
    if filter_by_name:
        names = [name.strip() for name in filter_by_name.split(',')]
        kfilter['name__iregex'] = r"^.*" + ('|'.join([name for name in names if name])) + r".*$"

    page_count = math_ceil(get_user_model().objects.filter(**kfilter).exclude(**kexclude).exclude(role='Admin').count() / limit) or 1

    page_offset = get_page_offset(offset_in_params=params.get('offset', ''), page_count=page_count)
    offset = (page_offset - 1) * limit

    users = get_user_model().objects.filter(**kfilter).exclude(**kexclude).exclude(role='Admin').order_by('-id')[offset:(offset + limit)]

    context = {
        "suffix_utc": '' if not timezone.get_current_timezone_name() == 'UTC' else 'UTC',
        "users": users,
        "user_conditions": {
            "page_range": range(1, page_count + 1),
            "limits": [4, 8, 16],
            "path_name": path_name,
            "limit": limit,
            "include_limit_exclude_offset_url": f"{reverse(path_name)}?limit={limit}",
            "page_offset": page_offset,
            'filter_by_name': filter_by_name,
        },
    }
    return render(request, "practice/users.html", context)


@ensure_is_admin
def view_unlocked_users_by_admin(request):
    return view_users_by_admin(request=request, path_name='practice:view_unlocked_users_by_admin', kexclude={'state': 'Locked'})


@ensure_is_admin
def view_locked_users_by_admin(request):
    return view_users_by_admin(request=request, path_name='practice:view_locked_users_by_admin', kfilter={'state': 'Locked'})


@ensure_is_admin
def process_user_by_admin(request, user_id):
    if request.method != 'POST':
        return HttpResponseBadRequest()

    user = get_object_or_404(get_user_model(), pk=user_id)
    # admin can not lock admin
    if user.role == 'Admin':
        return HttpResponseBadRequest()

    params = request.POST

    if params.get('unlock', '') == 'on' and user.state == 'Locked':
        user.state = 'Normal'
        user.save()
        request.session[notification_to_process_profile_key_name] = 'Mở khoá người dùng thành công'
    elif params.get('lock', '') == 'on' and user.state == 'Normal':
        user.state = 'Locked'
        user.save()
        # logout all session of this user
        for s in Session.objects.all():
            raw_session = s.get_decoded()
            if raw_session.get('_auth_user_id', 0) == user_id:
                s.delete()
                print(raw_session)
        request.session[notification_to_process_profile_key_name] = 'Khoá người dùng thành công'
    else:
        return HttpResponseBadRequest()

    return redirect(to="practice:process_profile", profile_id=user_id)


@ensure_is_admin
def process_question_tags_by_admin(request):
    path_name = "practice:process_question_tags_by_admin"
    filters_and_sorters_key_name = f'{path_name}__filters_and_sorters'
    data = {
        'name': {'errors': [], 'value': '', 'label': _('Nhãn câu hỏi mới')},
        'errors': [],
    }

    if request.method == 'GET':
        params = request.GET

        if (params.get('filter') or '') == 'input':
            request.session[filters_and_sorters_key_name] = {
                'filter_by_name': params.get('filter_by_name', ''),
            }
        elif not request.session.get(filters_and_sorters_key_name):
            request.session[filters_and_sorters_key_name] = {
                'filter_by_name': '',
            }

        _filters_and_sorters = request.session[filters_and_sorters_key_name]
        filter_by_name = _filters_and_sorters['filter_by_name']
        offset_in_params = params.get('offset', '')
    elif request.method == 'POST':
        params = request.POST

        is_valid = True
        data['name']['value'] = params.get('name', '')
        new_name = data['name']['value'].strip()
        if not new_name:
            is_valid = False
            data['name']['errors'].append(_('Nhãn phải có thể đọc.'))
        elif QuestionTag.objects.filter(name=new_name):
            is_valid = False
            data['name']['errors'].append(_('Nhãn đã tồn tại.'))

        if is_valid:
            qt = QuestionTag(name=data['name']['value'].strip())
            qt.save()
            data['name']['value'] = ''
            filter_by_name = ''
            offset_in_params = '1'
        else:
            _filters_and_sorters = request.session[filters_and_sorters_key_name]
            filter_by_name = _filters_and_sorters['filter_by_name']
            offset_in_params = params.get('offset', '')
    else:
        return HttpResponseBadRequest()

    limit = convert_to_non_negative_int(string=params.get('limit', ''), default=4)

    kfilter = {}
    if filter_by_name:
        names = [name.strip() for name in filter_by_name.split(',')]
        kfilter['name__iregex'] = r"^.*" + ('|'.join([name for name in names if name])) + r".*$"

    page_count = math_ceil(QuestionTag.objects.filter(**kfilter).count() / limit) or 1

    page_offset = get_page_offset(offset_in_params=offset_in_params, page_count=page_count)
    offset = (page_offset - 1) * limit

    question_tags = QuestionTag.objects.filter(**kfilter).order_by('-id')[offset:(offset + limit)]

    context = {
        "suffix_utc": '' if not timezone.get_current_timezone_name() == 'UTC' else 'UTC',
        "question_tags": question_tags,
        "data": data,
        "question_tag_conditions": {
            "page_range": range(1, page_count + 1),
            "limits": [4, 8, 16],
            "path_name": path_name,
            "limit": limit,
            "include_limit_exclude_offset_url": f"{reverse(path_name)}?limit={limit}",
            "page_offset": page_offset,
            'filter_by_name': filter_by_name,
        },
    }
    return render(request, "practice/question_tags.html", context)


"""
button unhide/hide_question			in evel detail (include question[*comment]+eval)
process_evals_by_admin (mark processed)		view detail
"""
