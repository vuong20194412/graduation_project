import datetime
import json
import math
import os
import pathlib
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.files import File
from django.db.models import Q, Count
from django.http import HttpResponseBadRequest as _HttpResponseBadRequest, HttpResponseNotFound, HttpResponseNotAllowed
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods
from sympy import preview as sympy_preview
from users.views import ensure_is_not_anonymous_user, ensure_is_admin, set_prev_adj_url

from .models import QuestionTag, Question, Answer, Comment, QuestionMedia, Log, QuestionEvaluation, CommentEvaluation


class HttpResponseBadRequest(_HttpResponseBadRequest):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.content = _('<h1>Lỗi đã xảy ra, vui lòng quay lại và tải lại.<h1>')


def convert_to_int(string: str, default: int = 0):
    return int(string) if re.match(string=string, pattern=re.compile('^-?[0-9]+$')) else default


def convert_to_non_negative_int(string: str, default: int = 0):
    return int(string) if re.match(string=string, pattern=re.compile('^[0-9]+$')) else default


def get_limit_offset_count(session, limit_in_params: str, limit_key_name: str, offset_in_params: str, records_count: int):
    if limit_key_name:
        limit = convert_to_non_negative_int(string=limit_in_params, default=0)
        if not limit:
            limit = session.get(limit_key_name, 4)
        elif limit != session.get(limit_key_name, 0):
            session[limit_key_name] = limit
    else:
        limit = convert_to_non_negative_int(string=limit_in_params, default=4)

    page_count = math.ceil(records_count / limit) or 1

    page_offset = convert_to_int(string=offset_in_params, default=1)
    if page_offset > 1:
        page_offset = page_offset if page_offset < page_count else page_count
    else:
        page_offset = page_count if page_offset == -1 else 1

    return limit, page_offset, page_count, (page_offset - 1) * limit


# Create your views here.
notification_to_process_profile_key_name = 'practice.views.process_profile___notification'
notification_to_view_detail_question_key_name = 'practice.views.view_detail_question__notification'
notification_to_process_evaluation_by_admin_key_name = 'practice.views.profile_key_name__notification'


def view_questions(request, path_name=None, filters=None):
    params = request.GET
    filters_and_sorters_key_name = f'{path_name}__filters_and_sorters'

    filters = filters or []

    tag_id = convert_to_int(string=params.get('tid', ''), default=-1)
    tag_name = ''
    tags = QuestionTag.objects.all()
    if tag_id != -1:
        tag = tags.filter(id=tag_id)
        if tag:
            filters.append(Q(tag_id=tag_id))
            tag_name = tag[0].name
        else:
            tag_id = -1

    if params.get('filter', '') == 'input':
        request.session[filters_and_sorters_key_name] = {
            'filter_by_created_at_from': params.get('filter_by_created_at_from', ''),
            'filter_by_created_at_to': params.get('filter_by_created_at_to', ''),
            'filter_by_content': params.get('filter_by_content', ''),
            'filter_by_hashtag': params.get('filter_by_hashtag', ''),
            'filter_by_author_code': params.get('filter_by_author_code', ''),
            'sorter_with_created_at': params.get('sorter_with_created_at', ''),
            'sorter_with_decreasing_number_of_answers': params.get('sorter_with_decreasing_number_of_answers', False),
            'sorter_with_decreasing_number_of_comments': params.get('sorter_with_decreasing_number_of_comments', False),
        }
    elif not request.session.get(filters_and_sorters_key_name):
        request.session[filters_and_sorters_key_name] = {
            'filter_by_created_at_from': '',
            'filter_by_created_at_to': '',
            'filter_by_content': '',
            'filter_by_hashtag': '',
            'filter_by_author_code': '',
            'sorter_with_created_at': '',
            'sorter_with_decreasing_number_of_answers': False,
            'sorter_with_decreasing_number_of_comments': False,
        }

    _filters_and_sorters = request.session[filters_and_sorters_key_name]

    created_at_from = _filters_and_sorters.get('filter_by_created_at_from', '')
    if created_at_from:
        created_at_from = datetime.datetime.strptime(created_at_from + ':00.000000', '%Y-%m-%dT%H:%M:%S.%f').replace(tzinfo=timezone.get_current_timezone())
        filters.append(Q(created_at__gte=created_at_from))

    created_at_to = _filters_and_sorters.get('filter_by_created_at_to', '')
    if created_at_to:
        created_at_to = datetime.datetime.strptime(created_at_to + ':59.999999', '%Y-%m-%dT%H:%M:%S.%f').replace(tzinfo=timezone.get_current_timezone())
        filters.append(Q(created_at__lte=created_at_to))

    contents = _filters_and_sorters.get('filter_by_content', '')
    if contents:
        contents = [content.strip() for content in contents.split(',') if content.strip()]
        if contents:
            filters.append(Q(content__iregex=r"^.*" + ('|'.join(contents)) + r".*$"))

    hashtags = _filters_and_sorters.get('filter_by_hashtag', '')
    if hashtags:
        hashtags = [hashtag.strip() for hashtag in hashtags.split(',') if hashtag.strip()]
        if hashtags:
            filters.append(Q(hashtags__iregex=r"^.*" + ('|'.join(hashtags)) + r".*$"))

    author_codes = _filters_and_sorters.get('filter_by_author_code', '')
    if author_codes:
        author_codes = [author_code.strip() for author_code in author_codes.split(',') if author_code.strip()]
        if author_codes:
            filters.append(Q(user__code__iregex=r"^.*" + ('|'.join(author_codes)) + r".*$"))

    limit, page_offset, page_count, offset = get_limit_offset_count(
        session=request.session,
        limit_in_params=params.get('limit', ''),
        limit_key_name='practice.views.view_questions__limit',
        offset_in_params=params.get('offset', ''),
        records_count=Question.objects.filter(*filters).distinct().count(),
    )

    order_bys = []
    k_alias = {}

    if _filters_and_sorters.get('sorter_with_decreasing_number_of_comments'):
        k_alias['comment__count'] = Count('comment')
        order_bys.append('-comment__count')

    if _filters_and_sorters.get('sorter_with_decreasing_number_of_answers'):
        k_alias['answer__count'] = Count('answer')
        order_bys.append('-answer__count')

    order_bys.append('created_at' if _filters_and_sorters.get('sorter_with_created_at', '') == '+' else '-created_at')

    questions = Question.objects.filter(*filters).alias(**k_alias).order_by(*order_bys).distinct()[offset:(offset + limit)]

    context = {
        "suffix_utc": '' if not timezone.get_current_timezone_name() == 'UTC' else 'UTC',
        "tags": tags,
        "questions": questions,
        "path_name": path_name,
        "include_limit_exclude_offset_url": f"{reverse(path_name)}?tid={tag_id}&limit={limit}",
        "question_conditions": {
            "page_range": range(1, page_count + 1),
            "limits": [4, 8, 16],
            "tag_id": tag_id,
            "tag_name": tag_name,
            "limit": limit,
            "page_offset": page_offset,
            'filter_by_created_at_from': _filters_and_sorters.get('filter_by_created_at_from', ''),
            'filter_by_created_at_to': _filters_and_sorters.get('filter_by_created_at_to', ''),
            'filter_by_content': _filters_and_sorters.get('filter_by_content', ''),
            'filter_by_hashtag': _filters_and_sorters.get('filter_by_hashtag', ''),
            'filter_by_author_code': _filters_and_sorters.get('filter_by_author_code', ''),
            'sorter_with_created_at': _filters_and_sorters.get('sorter_with_created_at', ''),
            'sorter_with_decreasing_number_of_answers': _filters_and_sorters.get('sorter_with_decreasing_number_of_answers', False),
            'sorter_with_decreasing_number_of_comments': _filters_and_sorters.get('sorter_with_decreasing_number_of_comments', False),
        },
    }

    return render(request, template_name='practice/questions.html', context=context)


@ensure_is_not_anonymous_user
@require_http_methods(['GET'])
def view_created_questions(request):
    return view_questions(request, path_name='practice:view_created_questions', filters=[Q(user_id=request.user.id)])


@ensure_is_not_anonymous_user
@require_http_methods(['GET'])
def view_answered_questions(request):
    return view_questions(request, path_name='practice:view_answered_questions', filters=[Q(answer__user_id=request.user.id), Q(state='Approved')])


@ensure_is_not_anonymous_user
@require_http_methods(['GET'])
def view_unanswered_questions(request):
    return view_questions(request, path_name='practice:view_unanswered_questions', filters=[~Q(answer__user_id=request.user.id), Q(state='Approved')])


@ensure_is_not_anonymous_user
@require_http_methods(['GET'])
def view_root(request):
    if request.user.role != 'Admin':
        return redirect("practice:view_unanswered_questions")
    else:
        return redirect("practice:view_pending_questions_by_admin")


@ensure_is_not_anonymous_user
def process_profile(request, profile_id):
    if request.method == 'GET':
        params = request.GET

        http_code = params.get('http_code')
        if http_code == '400':
            return HttpResponseBadRequest()
        elif http_code == '404':
            return HttpResponseNotFound(_('<h1>Not Found</h1>'))

        notification = request.session.get(notification_to_process_profile_key_name, '')
        if notification:
            notification = _(notification)
            request.session[notification_to_process_profile_key_name] = ''

        profile = get_user_model().objects.filter(id=profile_id)
        if not profile:
            return HttpResponseNotFound(_('<h1>Not Found</h1>'))
        profile = profile[0]

        data = {
            'name': {'errors': [], 'value': profile.name, 'label': _('Họ và tên')},
            'email': {'errors': [], 'value': profile.email, 'label': _('Email')},
            'code': {'value': profile.code, 'label': _('Mã người dùng')},
            'errors': [],
            'previous_adjacent_url': set_prev_adj_url(request),
            'readonly': profile.id != request.user.id,
        }

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

                data_errors = data_in_params.get('errors')
                if data_errors and isinstance(data_errors, type(data['errors'])):
                    data['errors'] = data_errors

            except (UnicodeDecodeError, ValueError):
                pass

        context = {
            "suffix_utc": '' if not timezone.get_current_timezone_name() == 'UTC' else 'UTC',
            'notification': notification,
            'profile_id': profile_id,
            'profile_locked': profile.state == 'Locked',
            'profile_role': profile.role,
            'data': data,
        }
        return render(request, template_name='practice/profile.html', context=context)

    elif request.method == 'POST':
        profile = get_user_model().objects.filter(id=profile_id)
        if not profile:
            return redirect(to=f"{reverse('practice:process_profile', args=[profile_id])}?http_code=404")
        profile = profile[0]

        if profile.id != request.user.id:
            return redirect(to=f"{reverse('practice:process_profile', args=[profile_id])}?http_code=400")

        data = {
            'name': {'errors': [], 'value': ''},
            'email': {'errors': [], 'value': ''},
            'errors': [],
        }

        is_valid = True
        params = request.POST

        data['email']['value'] = params.get('email', '')
        email = data['email']['value'].strip()
        if not email:
            is_valid = False
            data['email']['errors'].append('Trường này không được để trống.')
        else:
            if len(email) > 255:
                is_valid = False
                data['email']['errors'].append('Trường này không được nhập quá 255 ký tự.')

            if not re.match(pattern=re.compile(r'^[^@\[\]<>(),:;.\s\\\"]+(\.[^@\[\]<>(),:;.\s\\\"]+)*@([^@\[\]<>(),:;.\s\\\"]+\.)+[^@\[\]<>(),:;.\s\\\"]{2,}$'), string=email):
                is_valid = False
                data['email']['errors'].append('Email không đúng định dạng.')
            elif get_user_model().objects.filter(email=get_user_model().objects.normalize_email(email)).exclude(id=profile.id):
                is_valid = False
                data['email']['errors'].append('Email đã được đăng ký với tài khoản khác.')

        data['name']['value'] = params.get('name', '')
        name = data['name']['value'].strip()
        if not name:
            is_valid = False
            data['name']['errors'].append('Trường này không được để trống.')
        else:
            if len(name) > 255:
                is_valid = False
                data['name']['errors'].append('Trường này không được nhập quá 255 ký tự.')

        if is_valid:
            has_changed = False

            if profile.name != name:
                profile.name = name
                has_changed = True

            normalize_email = get_user_model().objects.normalize_email(email)
            if profile.email != normalize_email:
                profile.email = normalize_email
                has_changed = True

            if has_changed:
                profile.save()

            request.session[notification_to_process_profile_key_name] = "Thực hiện sửa thông tin thành công"
            return redirect(to='practice:process_profile', profile_id=profile_id)

        data_in_params = urlsafe_base64_encode(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        return redirect(to=f"{reverse('practice:process_profile', args=[profile_id])}?data={data_in_params}")

    else:
        return HttpResponseNotAllowed(['GET', 'POST'])


@ensure_is_not_anonymous_user
def process_new_question(request):
    if request.method == 'GET':
        default_choice = {'content': '', 'is_true': False}
        data = {
            'tag_id': {'errors': [], 'value': 0, 'label': _('Nhãn câu hỏi')},
            'hashtags': {'errors': [], 'value': [], 'label': _('Các hashtag')},
            'content': {'errors': [], 'value': '', 'label': _('Nội dung câu hỏi')},
            'latex_content': {'errors': [], 'value': '', 'label': _('Bổ sung nội dung câu hỏi bằng latex')},
            'choices': {'errors': [], 'value': [default_choice, default_choice, default_choice, default_choice],
                        'label': _('Các lựa chọn'), 'hint': _('tối thiểu phải có 2 lựa chọn có nội dung, có ít nhất 1 lựa chọn có nội dung là lựa chọn đúng')},
            'image': {'errors': [], 'value': '', 'label': _('Hình ảnh'),
                      'hint': _('1 tệp *.png, *.jpg hoặc *.jpeg và kích thước dưới ') + f'{QuestionMedia.MAX_IMAGE_SIZE}MB', 'notes': []},
            'video': {'errors': [], 'value': '', 'label': _('Video'),
                      'hint': _('1 tệp *.mp4 và kích thước dưới ') + f'{QuestionMedia.MAX_VIDEO_SIZE}MB', 'notes': []},
            'audio': {'errors': [], 'value': '', 'label': _('Audio'),
                      'hint': _('1 tệp *.mp3 và kích thước dưới ') + f'{QuestionMedia.MAX_AUDIO_SIZE}MB', 'notes': []},
            'errors': [],
            'previous_adjacent_url': set_prev_adj_url(request),
        }

        referer_url = request.META.get('HTTP_REFERER')
        if referer_url and (
                referer_url.startswith(request.build_absolute_uri(reverse('practice:view_created_questions'))) or
                referer_url.startswith(request.build_absolute_uri(reverse('practice:view_unanswered_questions'))) or
                referer_url.startswith(request.build_absolute_uri(reverse('practice:view_answered_questions')))
        ):
            match = re.search(pattern=re.compile(r'\?tid=[0-9]+'), string=referer_url)
            if match:
                tid = match.string[match.regs[0][0] + len('?tid='): match.regs[0][1]]
                data['tag_id']['value'] = convert_to_non_negative_int(tid)

        params = request.GET

        context = {
            'tags': QuestionTag.objects.all(),
        }

        data_in_params = params.get('data')
        if data_in_params:
            try:
                data_in_params = json.loads(urlsafe_base64_decode(data_in_params).decode('utf-8'))
                if 'tag_id' in data_in_params and isinstance(data_in_params['tag_id'], dict):
                    tag_id_errors = data_in_params['tag_id'].get('errors')
                    if tag_id_errors and isinstance(tag_id_errors, type(data['tag_id']['errors'])):
                        for tag_id_error in tag_id_errors:
                            data['tag_id']['errors'].append(_(tag_id_error))
                    tag_id_value = data_in_params['tag_id'].get('value')
                    if tag_id_value and isinstance(tag_id_value, type(data['tag_id']['value'])):
                        data['tag_id']['value'] = tag_id_value

                if 'hashtags' in data_in_params and isinstance(data_in_params['hashtags'], dict):
                    hashtags_value = data_in_params['hashtags'].get('value')
                    if hashtags_value and isinstance(hashtags_value, type(data['hashtags']['value'])):
                        data['hashtags']['value'] = hashtags_value

                if 'content' in data_in_params and isinstance(data_in_params['content'], dict):
                    content_errors = data_in_params['content'].get('errors')
                    if content_errors and isinstance(content_errors, type(data['content']['errors'])):
                        for content_error in content_errors:
                            data['content']['errors'].append(_(content_error))
                    content_value = data_in_params['content'].get('value')
                    if content_value and isinstance(content_value, type(data['content']['value'])):
                        data['content']['value'] = content_value

                if 'latex_content' in data_in_params and isinstance(data_in_params['latex_content'], dict):
                    latex_content_errors = data_in_params['latex_content'].get('errors')
                    if latex_content_errors and isinstance(latex_content_errors, type(data['latex_content']['errors'])):
                        for latex_content_error in latex_content_errors:
                            data['latex_content']['errors'].append(_(latex_content_error))
                    latex_content_value = data_in_params['latex_content'].get('value')
                    if latex_content_value and isinstance(latex_content_value, type(data['latex_content']['value'])):
                        data['latex_content']['value'] = latex_content_value

                if 'choices' in data_in_params and isinstance(data_in_params['choices'], dict):
                    choices_errors = data_in_params['choices'].get('errors')
                    if choices_errors and isinstance(choices_errors, type(data['choices']['errors'])):
                        for choices_error in choices_errors:
                            data['choices']['errors'].append(_(choices_error))
                    choices_value = data_in_params['choices'].get('value')
                    if choices_value and isinstance(choices_value, type(data['choices']['value'])):
                        data['choices']['value'] = choices_value

                if 'image' in data_in_params and isinstance(data_in_params['image'], dict):
                    image_errors = data_in_params['image'].get('errors')
                    if image_errors and isinstance(image_errors, type(data['image']['errors'])):
                        for image_error in image_errors:
                            data['image']['errors'].append(_(image_error))
                    image_notes = data_in_params['image'].get('notes')
                    if image_notes and isinstance(image_notes, type(data['image']['notes'])):
                        for image_note in image_notes:
                            data['image']['notes'].append(_(image_note))

                if 'video' in data_in_params and isinstance(data_in_params['video'], dict):
                    video_errors = data_in_params['video'].get('errors')
                    if video_errors and isinstance(video_errors, type(data['video']['errors'])):
                        for video_error in video_errors:
                            data['video']['errors'].append(_(video_error))
                    video_notes = data_in_params['video'].get('notes')
                    if video_notes and isinstance(video_notes, type(data['video']['notes'])):
                        for video_note in video_notes:
                            data['video']['notes'].append(_(video_note))

                if 'audio' in data_in_params and isinstance(data_in_params['audio'], dict):
                    audio_errors = data_in_params['audio'].get('errors')
                    if audio_errors and isinstance(audio_errors, type(data['audio']['errors'])):
                        for audio_error in audio_errors:
                            data['audio']['errors'].append(_(audio_error))
                    audio_notes = data_in_params['audio'].get('notes')
                    if audio_notes and isinstance(audio_notes, type(data['audio']['notes'])):
                        for audio_note in audio_notes:
                            data['audio']['notes'].append(_(audio_note))

                data_errors = data_in_params.get('errors')
                if data_errors and isinstance(data_errors, type(data['errors'])):
                    data['errors'] = data_errors

                context['preview_question'] = data_in_params.get('preview_question')

                context['base_url'] = (request.scheme if request.scheme in ['http', 'https'] else 'http') + '://' + request.get_host() + '/'

                addition_image_filename = data_in_params.get('addition_image_filename')
                if addition_image_filename:
                    context['addition_image_url'] = settings.TMP_MEDIA_URL + addition_image_filename

                latex_image_filename = data_in_params.get('latex_image_filename')
                if latex_image_filename:
                    context['latex_image_url'] = settings.TMP_MEDIA_URL + latex_image_filename

                video_filename = data_in_params.get('video_filename')
                if video_filename:
                    context['video_url'] = settings.TMP_MEDIA_URL + video_filename

                audio_filename = data_in_params.get('audio_filename')
                if audio_filename:
                    context['audio_url'] = settings.TMP_MEDIA_URL + audio_filename

            except (UnicodeDecodeError, ValueError):
                pass

        context['data'] = data
        return render(request, "practice/new_question.html", context)

    elif request.method == 'POST':
        default_choice = {'content': '', 'is_true': False}
        data = {
            'tag_id': {'errors': [], 'value': 0},
            'hashtags': {'value': []},
            'content': {'errors': [], 'value': ''},
            'latex_content': {'errors': [], 'value': ''},
            'choices': {'errors': [], 'value': []},
            'image': {'errors': [], 'notes': []},
            'video': {'errors': [], 'notes': []},
            'audio': {'errors': [], 'notes': []},
            'errors': [],
        }

        is_valid = True

        image = request.FILES.get('image')
        if image:
            limit_image_file_size = QuestionMedia.MAX_IMAGE_SIZE * 1024 * 1024
            if image.content_type not in ('image/png', 'image/jpeg') or not image.name or (not image.name.endswith('.png') and not image.name.endswith('.jpg') and not image.name.endswith('.jpeg')):
                is_valid = False
                data['image']['errors'].append('Hình ảnh phải là ảnh .png, .jpg hoặc .jpeg')
                if image.size >= limit_image_file_size:
                    data['image']['errors'].append(f'Kích thước hình ảnh phải bé hơn {QuestionMedia.MAX_IMAGE_SIZE}MB')
            elif image.size >= limit_image_file_size:
                is_valid = False
                data['image']['errors'].append(f'Kích thước hình ảnh phải bé hơn {QuestionMedia.MAX_IMAGE_SIZE}MB')

        video = request.FILES.get('video')
        if video:
            limit_video_file_size = QuestionMedia.MAX_VIDEO_SIZE * 1024 * 1024
            if video.content_type != 'video/mp4' or not video.name or not video.name.endswith('.mp4'):
                is_valid = False
                data['video']['errors'].append('Video phải là video .mp4')
                if video.size >= limit_video_file_size:
                    data['video']['errors'].append(f'Kích thước hình video phải bé hơn {QuestionMedia.MAX_VIDEO_SIZE}MB')
            elif video.size >= limit_video_file_size:
                is_valid = False
                data['video']['errors'].append(f'Kích thước video phải bé hơn {QuestionMedia.MAX_VIDEO_SIZE}MB')

        audio = request.FILES.get('audio')
        if audio:
            limit_audio_file_size = QuestionMedia.MAX_AUDIO_SIZE * 1024 * 1024
            if audio.content_type != 'audio/mpeg' or not audio.name or not audio.name.endswith('.mp3'):
                is_valid = False
                data['audio']['errors'].append('Audio phải là audio .mp3')
                if audio.size >= limit_audio_file_size:
                    data['audio']['errors'].append(f'Kích thước audio phải bé hơn {QuestionMedia.MAX_AUDIO_SIZE}MB')
            elif audio.size >= limit_audio_file_size:
                is_valid = False
                data['audio']['errors'].append(f'Kích thước audio phải bé hơn {QuestionMedia.MAX_AUDIO_SIZE}MB')

        params = request.POST

        choices = []
        choice_order = 1
        choice_content_count = 0
        true_choice_count = 0
        valid_true_choice_count = 0
        while f'choice_content_{choice_order}' in params:
            choice_content = params.get(f'choice_content_{choice_order}', '')
            choice_is_true = params.get(f'choice_is_true_{choice_order}', False)
            data['choices']['value'].append({"content": choice_content, "is_true": choice_is_true})
            choice_content = choice_content.strip()
            if choice_is_true:
                true_choice_count += 1
            if choice_content:
                choices.append({"content": choice_content, "is_true": choice_is_true})
                choice_content_count += 1
                if choice_is_true:
                    valid_true_choice_count += 1
            choice_order += 1
        while choice_order <= 4:
            data['choices']['value'].append(default_choice)
            choice_order += 1
        if choice_content_count < 2:
            is_valid = False
            data['choices']['errors'].append('Phải có ít nhất 2 lựa chọn có nội dung.')
        if true_choice_count < 1:
            is_valid = False
            data['choices']['errors'].append('Phải có ít nhất 1 lựa chọn đúng.')
        elif valid_true_choice_count == 0:
            is_valid = False
            data['choices']['errors'].append('Lựa chọn đúng phải là 1 trong các lựa chọn có nội dung')

        data['content']['value'] = params.get('content', '')
        content = data['content']['value'].strip()
        if not content:
            is_valid = False
            data['content']['errors'].append('Trường này không được để trống.')

        hashtags = params.get('hashtags', '')
        if hashtags:
            data['hashtags']['value'] = hashtags.split(',')

        data['tag_id']['value'] = params.get('tag_id', '')
        tag_id = convert_to_non_negative_int(string=str(data['tag_id']['value']), default=0)
        tag_name = ''
        if tag_id == 0:
            is_valid = False
            data['tag_id']['errors'].append('Trường này không được để trống.')
        else:
            tag = QuestionTag.objects.filter(id=tag_id)
            if not tag:
                is_valid = False
                data['tag_id']['errors'].append('Nhãn này không hợp lệ.')
            else:
                data['tag_id']['value'] = tag[0].id
                tag_name = tag[0].name

        data['latex_content']['value'] = params.get('latex_content', '')
        latex_content = data['latex_content']['value'].strip()
        latex_image_pathname = ''
        if latex_content:
            latex_image_filename = f"{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S%f')}{request.user.code[1:]}latex.png"
            latex_image_pathname = pathlib.Path(settings.TMP_MEDIA_ROOT, latex_image_filename)
            with open(latex_image_pathname, 'wb+'):
                pass
            try:
                extra_preamble = ("\\usepackage[utf8]{inputenc}\n"
                                  "\\DeclareUnicodeCharacter{1EA0}{\\text{A}}"
                                  "\\DeclareUnicodeCharacter{1EA1}{\\text{a}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EA2}{\\text{A}}"
                                  "\\DeclareUnicodeCharacter{1EA3}{\\text{a}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EA4}{\\text{A}}"
                                  "\\DeclareUnicodeCharacter{1EA5}{\\text{a}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EAE}{\\text{A}}"
                                  "\\DeclareUnicodeCharacter{1EAF}{\\text{a}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EB0}{\\text{A}}"
                                  "\\DeclareUnicodeCharacter{1EB1}{\\text{a}}" #ằ
                                  
                                  "\\DeclareUnicodeCharacter{1EB2}{\\text{A}}"
                                  "\\DeclareUnicodeCharacter{1EB3}{\\text{a}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EB4}{\\text{A}}"
                                  "\\DeclareUnicodeCharacter{1EB5}{\\text{a}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EB6}{\\text{A}}"
                                  "\\DeclareUnicodeCharacter{1EB7}{\\text{a}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EA6}{\\text{A}}"
                                  "\\DeclareUnicodeCharacter{1EA7}{\\text{a}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EA8}{\\text{A}}"
                                  "\\DeclareUnicodeCharacter{1EA9}{\\text{a}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EAA}{\\text{A}}"
                                  "\\DeclareUnicodeCharacter{1EAB}{\\text{a}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EAC}{\\text{A}}"
                                  "\\DeclareUnicodeCharacter{1EAD}{\\text{a}}"
                                  
                                  "\\DeclareUnicodeCharacter{0110}{\\text{D}}"
                                  "\\DeclareUnicodeCharacter{0111}{\\text{d}}" #đ
                                  
                                  "\\DeclareUnicodeCharacter{1EBA}{\\text{e}}"
                                  "\\DeclareUnicodeCharacter{1EBB}{\\text{e}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EBC}{\\text{e}}"
                                  "\\DeclareUnicodeCharacter{1EBD}{\\text{e}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EBE}{\\text{e}}"
                                  "\\DeclareUnicodeCharacter{1EBF}{\\text{e}}" #ế
                                  
                                  "\\DeclareUnicodeCharacter{1EB8}{\\text{e}}"
                                  "\\DeclareUnicodeCharacter{1EB9}{\\text{e}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EC0}{\\text{e}}"
                                  "\\DeclareUnicodeCharacter{1EC1}{\\text{e}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EC2}{\\text{e}}"
                                  "\\DeclareUnicodeCharacter{1EC3}{\\text{e}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EC4}{\\text{e}}"
                                  "\\DeclareUnicodeCharacter{1EC5}{\\text{e}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EC6}{\\text{e}}"
                                  "\\DeclareUnicodeCharacter{1EC7}{\\text{e}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EC8}{\\text{I}}"                      
                                  "\\DeclareUnicodeCharacter{1EC9}{\\text{i}}"
                                  
                                  "\\DeclareUnicodeCharacter{1ECA}{\\text{I}}"
                                  "\\DeclareUnicodeCharacter{1ECB}{\\text{i}}"
                                  
                                  "\\DeclareUnicodeCharacter{1ECC}{\\text{O}}"
                                  "\\DeclareUnicodeCharacter{1ECD}{\\text{o}}"
                                  
                                  "\\DeclareUnicodeCharacter{1ECE}{\\text{O}}"
                                  "\\DeclareUnicodeCharacter{1ECF}{\\text{o}}"
                                  
                                  "\\DeclareUnicodeCharacter{1ED0}{\\text{O}}"
                                  "\\DeclareUnicodeCharacter{1ED1}{\\text{o}}"
                                  
                                  "\\DeclareUnicodeCharacter{1ED2}{\\text{O}}"
                                  "\\DeclareUnicodeCharacter{1ED3}{\\text{o}}"
                                  
                                  "\\DeclareUnicodeCharacter{1ED4}{\\text{O}}"
                                  "\\DeclareUnicodeCharacter{1ED5}{\\text{o}}"
                                  
                                  "\\DeclareUnicodeCharacter{1ED6}{\\text{O}}"
                                  "\\DeclareUnicodeCharacter{1ED7}{\\text{o}}"
                                  
                                  "\\DeclareUnicodeCharacter{1ED8}{\\text{O}}"
                                  "\\DeclareUnicodeCharacter{1ED9}{\\text{o}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EDA}{\\text{O}}"
                                  "\\DeclareUnicodeCharacter{1EDB}{\\text{o}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EDC}{\\text{O}}"
                                  "\\DeclareUnicodeCharacter{1EDD}{\\text{o}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EDE}{\\text{O}}"
                                  "\\DeclareUnicodeCharacter{1EDF}{\\text{o}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EE0}{\\text{O}}"
                                  "\\DeclareUnicodeCharacter{1EE1}{\\text{o}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EE2}{\\text{O}}"
                                  "\\DeclareUnicodeCharacter{1EE3}{\\text{o}}"
                                  
                                  "\\DeclareUnicodeCharacter{01A0}{\\text{O}}"
                                  "\\DeclareUnicodeCharacter{01A1}{\\text{o}}" #ơ
                                  
                                  "\\DeclareUnicodeCharacter{1EE4}{\\text{U}}"
                                  "\\DeclareUnicodeCharacter{1EE5}{\\text{u}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EE6}{\\text{U}}"
                                  "\\DeclareUnicodeCharacter{1EE7}{\\text{u}}"
                                  
                                  "\\DeclareUnicodeCharacter{01AF}{\\text{U}}"
                                  "\\DeclareUnicodeCharacter{01B0}{\\text{u}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EE8}{\\text{U}}"
                                  "\\DeclareUnicodeCharacter{1EE9}{\\text{u}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EEA}{\\text{U}}"
                                  "\\DeclareUnicodeCharacter{1EEB}{\\text{u}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EEC}{\\text{U}}"
                                  "\\DeclareUnicodeCharacter{1EED}{\\text{u}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EEE}{\\text{U}}"
                                  "\\DeclareUnicodeCharacter{1EEF}{\\text{u}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EF0}{\\text{U}}"
                                  "\\DeclareUnicodeCharacter{1EF1}{\\text{u}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EF4}{\\text{Y}}"
                                  "\\DeclareUnicodeCharacter{1EF5}{\\text{y}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EF6}{\\text{Y}}"
                                  "\\DeclareUnicodeCharacter{1EF7}{\\text{y}}"
                                  
                                  "\\DeclareUnicodeCharacter{1EF8}{\\text{Y}}"
                                  "\\DeclareUnicodeCharacter{1EF9}{\\text{y}}"
                                  )
                sympy_preview(latex_content, viewer='file', extra_preamble=extra_preamble, filename=latex_image_pathname, euler=False)
                data['latex_image_filename'] = latex_image_filename
            except Exception as e:
                if str(e).startswith("'latex' exited abnormally with the following output:"):
                    data['latex_content']['errors'].append('Nội dung latex không đúng cú pháp')
                else:
                    data['latex_content']['errors'].append('Có lỗi xảy ra, vui lòng thay đổi nội dung latex và thử lại')

        if not image and params.get('using_old_image') and params.get('old_addition_image_url'):
            old_addition_image_url = params.get('old_addition_image_url')
            if not old_addition_image_url.startswith(settings.TMP_MEDIA_URL) or (not old_addition_image_url.endswith('.png') and not old_addition_image_url.endswith('.jpg') and not old_addition_image_url.endswith('.jpeg')):
                is_valid = False
                data['image']['errors'].append('Có lỗi xảy ra, vui lòng thực hiện chọn ảnh thủ công')
            else:
                addition_image_filename = old_addition_image_url[len(settings.TMP_MEDIA_URL):]
                # prefix = f"{datetime.datetime.now(datetime.timezone.utc). strf time('%Y%m%d%H%M%S%f')}{request.user.code[1:]}addition_"
                exclude_datetime_prefix_filename = f"{request.user.code[1:]}addition_"
                if (len(addition_image_filename) <= 20 + len(exclude_datetime_prefix_filename)
                        or not addition_image_filename[20:].startswith(exclude_datetime_prefix_filename)
                        or not re.match(
                            pattern=re.compile(r'^((000[1-9])|(00[1-9][0-9])|(0[1-9][0-9]{2})|([1-9][0-9]{3}))'
                                               r'((0[1-9])|(1[0-2]))((0[1-9])|([1-2][0-9])|(3[0-1]))'
                                               r'(([0-1][0-9])|(2[0-3]))[0-5][0-9][0-5][0-9][0-9]{6}$'),
                            string=addition_image_filename[0:20])):
                    is_valid = False
                    data['image']['errors'].append('Có lỗi xảy ra, vui lòng thực hiện chọn ảnh thủ công')
                else:
                    addition_image_pathname = pathlib.Path(settings.TMP_MEDIA_ROOT, addition_image_filename)
                    if not os.path.exists(addition_image_pathname):
                        is_valid = False
                        data['image']['errors'].append('Có lỗi xảy ra, vui lòng thực hiện chọn ảnh thủ công')
                    else:
                        data['addition_image_filename'] = addition_image_filename

        if not video and params.get('using_old_video') and params.get('old_video_url'):
            old_video_url = params.get('old_video_url')
            if not old_video_url.startswith(settings.TMP_MEDIA_URL) or not old_video_url.endswith('.mp4'):
                is_valid = False
                data['video']['errors'].append('Có lỗi xảy ra, vui lòng thực hiện chọn video thủ công')
            else:
                video_filename = old_video_url[len(settings.TMP_MEDIA_URL):]
                # prefix = f"{datetime.datetime.now(datetime.timezone.utc). strf time('%Y%m%d%H%M%S%f')}{request.user.code[1:]}"
                exclude_datetime_prefix_filename = f"{request.user.code[1:]}"
                if (len(video_filename) <= 20 + len(exclude_datetime_prefix_filename)
                        or not video_filename[20:].startswith(exclude_datetime_prefix_filename)
                        or not re.match(
                            pattern=re.compile(r'^((000[1-9])|(00[1-9][0-9])|(0[1-9][0-9]{2})|([1-9][0-9]{3}))'
                                               r'((0[1-9])|(1[0-2]))((0[1-9])|([1-2][0-9])|(3[0-1]))'
                                               r'(([0-1][0-9])|(2[0-3]))[0-5][0-9][0-5][0-9][0-9]{6}$'),
                            string=video_filename[0:20])):
                    is_valid = False
                    data['video']['errors'].append('Có lỗi xảy ra, vui lòng thực hiện chọn video thủ công')
                else:
                    video_pathname = pathlib.Path(settings.TMP_MEDIA_ROOT, video_filename)
                    if not os.path.exists(video_pathname):
                        is_valid = False
                        data['video']['errors'].append('Có lỗi xảy ra, vui lòng thực hiện chọn video thủ công')
                    else:
                        data['video_filename'] = video_filename

        if not audio and params.get('using_old_audio') and params.get('old_audio_url'):
            old_audio_url = params.get('old_audio_url')
            if not old_audio_url.startswith(settings.TMP_MEDIA_URL) or not old_audio_url.endswith('.mp3'):
                is_valid = False
                data['audio']['errors'].append('Có lỗi xảy ra, vui lòng thực hiện chọn audio thủ công')
            else:
                audio_filename = old_audio_url[len(settings.TMP_MEDIA_URL):]
                # prefix = f"{datetime.datetime.now(datetime.timezone.utc). strf time('%Y%m%d%H%M%S%f')}{request.user.code[1:]}addition_"
                exclude_datetime_prefix_filename = f"{request.user.code[1:]}"
                if (len(audio_filename) <= 20 + len(exclude_datetime_prefix_filename)
                        or not audio_filename[20:].startswith(exclude_datetime_prefix_filename)
                        or not re.match(
                            pattern=re.compile(r'^((000[1-9])|(00[1-9][0-9])|(0[1-9][0-9]{2})|([1-9][0-9]{3}))'
                                               r'((0[1-9])|(1[0-2]))((0[1-9])|([1-2][0-9])|(3[0-1]))'
                                               r'(([0-1][0-9])|(2[0-3]))[0-5][0-9][0-5][0-9][0-9]{6}$'),
                            string=audio_filename[0:20])):
                    is_valid = False
                    data['audio']['errors'].append('Có lỗi xảy ra, vui lòng thực hiện chọn audio thủ công')
                else:
                    audio_pathname = pathlib.Path(settings.TMP_MEDIA_ROOT, audio_filename)
                    if not os.path.exists(audio_pathname):
                        is_valid = False
                        data['audio']['errors'].append('Có lỗi xảy ra, vui lòng thực hiện chọn audio thủ công')
                    else:
                        data['audio_filename'] = audio_filename

        if params.get('preview'):
            hashtags = set()
            for hashtag in data['hashtags']['value']:
                hashtag = hashtag.strip()
                if hashtag:
                    hashtags.add(hashtag)

            data['preview_question'] = {
                'content': content,
                'choices': choices,
                'tag_name': tag_name,
                'hashtags': ','.join(hashtags),
                'get_display_hashtags': f'#{" #".join(hashtags)}' if hashtags else '',
            }

            if image and not data['image']['errors']:
                addition_image_filename = f"{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S%f')}{request.user.code[1:]}addition_{image.name}"
                addition_image_pathname = pathlib.Path(settings.TMP_MEDIA_ROOT, addition_image_filename)
                with open(addition_image_pathname, 'wb+') as f:
                    for chunk in image.chunks():
                        f.write(chunk)
                data['addition_image_filename'] = addition_image_filename

            if video and not data['video']['errors']:
                video_filename = f"{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S%f')}{request.user.code[1:]}{video.name}"
                video_pathname = pathlib.Path(settings.TMP_MEDIA_ROOT, video_filename)
                with open(video_pathname, 'wb+') as f:
                    for chunk in video.chunks():
                        f.write(chunk)
                data['video_filename'] = video_filename

            if audio and not data['audio']['errors']:
                audio_filename = f"{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S%f')}{request.user.code[1:]}{audio.name}"
                audio_pathname = pathlib.Path(settings.TMP_MEDIA_ROOT, audio_filename)
                with open(audio_pathname, 'wb+') as f:
                    for chunk in audio.chunks():
                        f.write(chunk)
                data['audio_filename'] = audio_filename

        elif is_valid:
            hashtags = set()
            for hashtag in data['hashtags']['value']:
                hashtag = hashtag.strip()
                if hashtag:
                    hashtags.add(hashtag)

            create_at = datetime.datetime.now(datetime.timezone.utc)

            q = Question(content=content,
                         state='Pending',
                         choices=choices,
                         tag_id=tag_id,
                         user_id=request.user.id,
                         hashtags=','.join(hashtags),
                         created_at=create_at)
            q.save()

            if latex_image_pathname:
                qm = QuestionMedia(name='question_latex_image',
                                   media_type='image',
                                   question_id=q.id,
                                   created_at=create_at)
                with open(latex_image_pathname, 'rb') as f:
                    data = File(f)
                    qm.file.save('latex.png', data)
                qm.save()

            if image:
                qm = QuestionMedia(name='question_addition_image',
                                   media_type='image',
                                   question_id=q.id,
                                   file=image,
                                   created_at=create_at)
                qm.save()
            elif params.get('using_old_image') and params.get('old_addition_image_url'):
                addition_image_filename = params.get('old_addition_image_url', '')[len(settings.TMP_MEDIA_URL):]
                addition_image_pathname = pathlib.Path(settings.TMP_MEDIA_ROOT, addition_image_filename)
                if os.path.exists(addition_image_pathname):
                    qm = QuestionMedia(name='question_addition_image',
                                       media_type='image',
                                       question_id=q.id,
                                       created_at=create_at)
                    with open(addition_image_pathname, 'rb') as f:
                        data = File(f)
                        qm.file.save(addition_image_filename[(20 + len(f'{request.user.code[1:]}addition_')):], data)
                    qm.save()

            if video:
                qm = QuestionMedia(name='question_video',
                                   media_type='video',
                                   question_id=q.id,
                                   file=video,
                                   created_at=create_at)
                qm.save()
            elif params.get('using_old_video') and params.get('old_video_url'):
                video_filename = params.get('old_video_url', '')[len(settings.TMP_MEDIA_URL):]
                video_pathname = pathlib.Path(settings.TMP_MEDIA_ROOT, video_filename)
                if os.path.exists(video_pathname):
                    qm = QuestionMedia(name='question_video',
                                       media_type='video',
                                       question_id=q.id,
                                       created_at=create_at)
                    with open(video_pathname, 'rb') as f:
                        data = File(f)
                        qm.file.save(video_filename[(20 + len(f'{request.user.code[1:]}')):], data)
                    qm.save()

            if audio:
                qm = QuestionMedia(name='question_audio',
                                   media_type='audio',
                                   question_id=q.id,
                                   file=audio,
                                   created_at=create_at)
                qm.save()
            elif params.get('using_old_audio') and params.get('old_audio_url'):
                audio_filename = params.get('old_audio_url', '')[len(settings.TMP_MEDIA_URL):]
                audio_pathname = pathlib.Path(settings.TMP_MEDIA_ROOT, audio_filename)
                if os.path.exists(audio_pathname):
                    qm = QuestionMedia(name='question_audio',
                                       media_type='audio',
                                       question_id=q.id,
                                       created_at=create_at)
                    with open(audio_pathname, 'rb') as f:
                        data = File(f)
                        qm.file.save(audio_filename[(20 + len(f'{request.user.code[1:]}')):], data)
                    qm.save()

            request.session[notification_to_view_detail_question_key_name] = "Thực hiện tạo câu hỏi thành công"
            return redirect(to='practice:view_detail_question', question_id=q.id)

        if not data['image']['errors'] and image and not params.get('preview'):
            data['image']['notes'].append('Lưu ý: Chọn ảnh nếu cần thiết.')

        if not data['video']['errors'] and video and not params.get('preview'):
            data['video']['notes'].append('Lưu ý: Chọn video nếu cần thiết.')

        if not data['audio']['errors'] and audio and not params.get('preview'):
            data['audio']['notes'].append('Lưu ý: Chọn audio nếu cần thiết.')

        data_in_params = urlsafe_base64_encode(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        return redirect(to=f"{reverse('practice:process_new_question')}?data={data_in_params}")

    else:
        return HttpResponseNotAllowed(['GET', 'POST'])


@ensure_is_not_anonymous_user
def process_new_answer(request, question_id):
    if request.method == 'GET':
        params = request.GET

        http_code = params.get('http_code')
        if http_code == '404':
            return HttpResponseNotFound(_('<h1>Not Found</h1>'))

        question = Question.objects.filter(id=question_id, state='Approved')
        if not question:
            return HttpResponseNotFound(_('<h1>Not Found</h1>'))
        question = question[0]

        data = {
            'choices': {'value': [], 'errors': [], 'label': _('Lựa chọn')},
            'errors': [],
            'previous_adjacent_url': set_prev_adj_url(request),
        }

        data_in_params = params.get('data')
        if data_in_params:
            try:
                data_in_params = json.loads(urlsafe_base64_decode(data_in_params).decode('utf-8'))

                if 'choices' in data_in_params and isinstance(data_in_params['choices'], dict):
                    choices_errors = data_in_params['choices'].get('errors')
                    if choices_errors and isinstance(choices_errors, type(data['choices']['errors'])):
                        for choices_error in choices_errors:
                            data['choices']['errors'].append(_(choices_error))
                    choices_value = data_in_params['choices'].get('value')
                    if choices_value and isinstance(choices_value, type(data['choices']['value'])):
                        data['choices']['value'] = choices_value

                data_errors = data_in_params.get('errors')
                if data_errors and isinstance(data_errors, type(data['errors'])):
                    data['errors'] = data_errors

            except (UnicodeDecodeError, ValueError):
                pass

        context = {
            'question': question,
            'data': data,
            "question_addition_image": question.get_addition_image(),
            "question_latex_image": question.get_latex_image(),
            "question_video": question.get_video(),
            "question_audio": question.get_audio(),
        }
        return render(request, "practice/new_answer.html", context)

    elif request.method == 'POST':
        question = Question.objects.filter(id=question_id, state='Approved')
        if not question:
            return redirect(to=f"{reverse('practice:process_new_answer')}?http_code=404")
        question = question[0]

        data = {
            'choices': {'value': [], 'errors': []},
            'errors': [],
        }

        is_valid = True
        params = request.POST

        data['choices']['value'] = []
        if question.is_single_choice():
            choice = params.get('choice', '')
            if not choice:
                is_valid = False
                data['choices']['errors'].append('Phải chọn 1 lựa chọn.')
            else:
                choice = convert_to_non_negative_int(string=choice)
                if 1 <= choice <= len(question.choices):
                    data['choices']['value'].append(choice)
                if not data['choices']['value']:
                    is_valid = False
                    data['choices']['errors'].append('Phải chọn 1 lựa chọn trong các lựa chọn.')
        else:
            choices = []
            for choice_order in range(1, len(question.choices) + 1):
                choice = params.get(f'choice_{choice_order}')
                if choice:
                    choices.append(choice)
            if not choices:
                is_valid = False
                data['choices']['errors'].append('Phải chọn ít nhất 1 lựa chọn.')
            else:
                for choice in choices:
                    choice = convert_to_non_negative_int(string=choice)
                    if 1 <= choice <= len(question.choices):
                        data['choices']['value'].append(choice)
                    if not data['choices']['value']:
                        is_valid = False
                        data['choices']['errors'].append('Phải chọn ít nhất 1 lựa chọn trong các lựa chọn.')

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

            request.session[notification_to_view_detail_question_key_name] = "Thực hiện tạo câu trả lời thành công"
            return redirect(to="practice:view_detail_question", question_id=question_id)

        data_in_params = urlsafe_base64_encode(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        return redirect(to=f"{reverse('practice:process_new_answer', args=[question_id])}?data={data_in_params}")

    else:
        return HttpResponseNotAllowed(['GET', 'POST'])


def view_question(request, question_id, showing_comments: bool = False):
    params = request.GET

    http_code = params.get('http_code')
    if http_code:
        if http_code == '400':
            return HttpResponseBadRequest()
        elif http_code == '404':
            return HttpResponseNotFound(_('<h1>Not Found</h1>'))

    notification = request.session.get(notification_to_view_detail_question_key_name, '')
    if notification:
        notification = _(notification)
        request.session[notification_to_view_detail_question_key_name] = ''

    if request.user.role != 'Admin':
        if not showing_comments:
            question = Question.objects.filter(Q(id=question_id), (Q(state='Approved') | Q(user_id=request.user.id)))
        else:
            question = Question.objects.filter(id=question_id, state='Approved')
    else:
        question = Question.objects.filter(id=question_id)

    if not question:
        return HttpResponseNotFound(_('<h1>Not Found</h1>'))
    question = question[0]

    past_answers = Answer.objects.filter(user_id=request.user.id, question_id=question_id)

    data = {
        'previous_adjacent_url': set_prev_adj_url(request),
    }

    question_rating, question_evaluation_count = question.get_rating()

    context = {
        "suffix_utc": '' if not timezone.get_current_timezone_name() == 'UTC' else 'UTC',
        "notification": notification,
        "question": question,
        "question_rating": '{:.2f}'.format(question_rating) if question_rating else '',
        "question_evaluation_count": question_evaluation_count,
        "past_answers": past_answers,
        "question_addition_image": question.get_addition_image(),
        "question_latex_image": question.get_latex_image(),
        "question_video": question.get_video(),
        "question_audio": question.get_audio(),
    }

    if showing_comments:
        data.update({
            "comment_content": {"errors": [], "value": "", "label": _('Bình luận mới')},
            "errors": [],
        })

        data_in_params = params.get('data')
        if data_in_params:
            try:
                data_in_params = json.loads(urlsafe_base64_decode(data_in_params).decode('utf-8'))

                if 'comment_content' in data_in_params and isinstance(data_in_params['comment_content'], dict):
                    comment_content_errors = data_in_params['comment_content'].get('errors')
                    if comment_content_errors and isinstance(comment_content_errors, type(data['comment_content']['errors'])):
                        for comment_content_error in comment_content_errors:
                            data['comment_content']['errors'].append(_(comment_content_error))
                    comment_content_value = data_in_params['comment_content'].get('value')
                    if comment_content_value and isinstance(comment_content_value, type(data['comment_content']['value'])):
                        data['comment_content']['value'] = comment_content_value

                data_errors = data_in_params.get('errors')
                if data_errors and isinstance(data_errors, type(data['errors'])):
                    data['errors'] = data_errors

            except (UnicodeDecodeError, ValueError):
                pass

        limit, page_offset, page_count, offset = get_limit_offset_count(
            session=request.session,
            limit_in_params=params.get('limit', ''),
            limit_key_name='practice.views.get_comments_in_question__limit',
            offset_in_params=params.get('offset', ''),
            records_count=question.comment_set.distinct().count()
        )

        comments = question.comment_set.filter(~Q(state='Locked')).order_by('-created_at').distinct()[offset:(offset + limit)]

        context.update({
            "showing_comments": True,
            "comments": comments,
            "comment_conditions": {
                "page_range": range(1, page_count + 1),
                "limits": [4, 8, 16],
                "page_offset": page_offset,
                "limit": limit,
                "include_limit_exclude_offset_url": f"{reverse('practice:process_comments_in_question', args=[question.id])}?limit={limit}",
            }
        })

    context["data"] = data
    return render(request, "practice/detail_question.html", context)


@ensure_is_not_anonymous_user
@require_http_methods(['GET'])
def view_detail_question(request, question_id):
    return view_question(request, question_id)


@ensure_is_not_anonymous_user
@require_http_methods(['GET'])
def view_detail_answer(request, answer_id):
    if request.user.role != 'Admin':
        answer = Answer.objects.filter(id=answer_id)
        if not answer:
            return HttpResponseNotFound(_('<h1>Not Found</h1>'))
        answer = answer[0]
    else:
        return HttpResponseBadRequest()

    data = {
        'previous_adjacent_url': set_prev_adj_url(request),
    }

    context = {
        "suffix_utc": '' if not timezone.get_current_timezone_name() == 'UTC' else 'UTC',
        "answer": answer,
        "data": data,
        "question_addition_image": answer.question.get_addition_image(),
        "question_latex_image": answer.question.get_latex_image(),
        "question_video": answer.question.get_video(),
        "question_audio": answer.question.get_audio(),
    }
    return render(request, "practice/detail_answer.html", context)


@ensure_is_not_anonymous_user
def process_comments_in_question(request, question_id):
    if request.method == 'GET':
        return view_question(request, question_id, showing_comments=True)

    elif request.method == 'POST':
        question = Question.objects.filter(id=question_id, state='Approved')
        if not question:
            return redirect(to=f"{reverse('practice:process_comments_in_question')}?http_code=404")
        question = question[0]

        data = {
            "comment_content": {"errors": [], "value": ""},
            "errors": []
        }

        is_valid = True
        params = request.POST

        data['comment_content']['value'] = params.get('comment_content', '')
        comment_content = data['comment_content']['value'].strip()
        if not comment_content:
            is_valid = False
            data['comment_content']['errors'].append('Bình luận phải có thể đọc.')

        if is_valid:
            c = Comment(
                content=comment_content,
                question_id=question.id,
                user_id=request.user.id,
                created_at=datetime.datetime.now(datetime.timezone.utc),
                updated_at=datetime.datetime.now(datetime.timezone.utc)
            )
            c.save()

            return redirect(to=f"{reverse('practice:process_comments_in_question', args=[question_id])}?limit={params.get('limit', '')}&offset=1")

        data_in_params = urlsafe_base64_encode(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        return redirect(to=f"{reverse('practice:process_comments_in_question', args=[question_id])}?limit={params.get('limit', '')}&offset={params.get('offset', '')}&data={data_in_params}")

    else:
        return HttpResponseNotAllowed(['GET', 'POST'])


@ensure_is_not_anonymous_user
def process_new_question_evaluation(request, question_id):
    if request.method == 'GET':
        params = request.GET

        http_code = params.get('http_code')
        if http_code == '404':
            return HttpResponseNotFound(_('<h1>Not Found</h1>'))

        question = Question.objects.filter(id=question_id, state='Approved')
        if not question:
            return HttpResponseNotFound(_('<h1>Not Found</h1>'))
        question = question[0]

        data = {
            'evaluation_content': {'errors': [], 'value': '', 'label': _('Đánh giá mới')},
            'question_rating': {'errors': [], 'value': '', 'label': _('Bình chọn số sao câu hỏi')},
            'errors': [],
            'previous_adjacent_url': set_prev_adj_url(request),
        }

        data_in_params = params.get('data')
        if data_in_params:
            try:
                data_in_params = json.loads(urlsafe_base64_decode(data_in_params).decode('utf-8'))

                if 'evaluation_content' in data_in_params and isinstance(data_in_params['evaluation_content'], dict):
                    evaluation_content_errors = data_in_params['evaluation_content'].get('errors')
                    if evaluation_content_errors and isinstance(evaluation_content_errors, type(data['evaluation_content']['errors'])):
                        for evaluation_content_error in evaluation_content_errors:
                            data['evaluation_content']['errors'].append(_(evaluation_content_error))
                    evaluation_content_value = data_in_params['evaluation_content'].get('value')
                    if evaluation_content_value and isinstance(evaluation_content_value, type(data['evaluation_content']['value'])):
                        data['evaluation_content']['value'] = evaluation_content_value

                if 'question_rating' in data_in_params and isinstance(data_in_params['question_rating'], dict):
                    question_rating_errors = data_in_params['question_rating'].get('errors')
                    if question_rating_errors and isinstance(question_rating_errors, type(data['question_rating']['errors'])):
                        for question_rating_error in question_rating_errors:
                            data['question_rating']['errors'].append(_(question_rating_error))
                    question_rating_value = data_in_params['question_rating'].get('value')
                    if question_rating_value and isinstance(question_rating_value, type(data['question_rating']['value'])):
                        data['question_rating']['value'] = question_rating_value

                data_errors = data_in_params.get('errors')
                if data_errors and isinstance(data_errors, type(data['errors'])):
                    data['errors'] = data_errors

            except (UnicodeDecodeError, ValueError):
                pass

        context = {
            "suffix_utc": '' if not timezone.get_current_timezone_name() == 'UTC' else 'UTC',
            "question": question,
            "data": data,
            "question_rating_range": ['1', '2', '3', '4', '5'],
            "question_addition_image": question.get_addition_image(),
            "question_latex_image": question.get_latex_image(),
            "question_video": question.get_video(),
            "question_audio": question.get_audio(),
        }
        return render(request, "practice/new_question_evaluation.html", context)

    elif request.method == 'POST':
        question = Question.objects.filter(id=question_id, state='Approved')
        if not question:
            return redirect(to=f"{reverse('practice:process_new_question_evaluation')}?http_code=404")
        question = question[0]

        data = {
            'evaluation_content': {'errors': [], 'value': ''},
            'question_rating': {'errors': [], 'value': ''},
            'errors': [],
        }

        params = request.POST
        is_valid = True

        data['evaluation_content']['value'] = params.get('evaluation_content', '')
        evaluation_content = data['evaluation_content']['value'].strip()

        data['question_rating']['value'] = params.get('question_rating', '')
        question_rating = convert_to_int(string=data['question_rating']['value'].strip())

        if question_rating not in [1,2,3,4,5] and not evaluation_content:
            is_valid = False
            data['errors'].append('Đánh giá bằng nhập nội dung, số sao hoặc cả hai')

        if is_valid:
            qe = QuestionEvaluation(
                content=evaluation_content,
                question_id=question.id,
                user_id=request.user.id,
                created_at=datetime.datetime.now(datetime.timezone.utc),
                updated_at=datetime.datetime.now(datetime.timezone.utc),
            )
            if question_rating and question_rating in [1, 2, 3, 4, 5]:
                qe.question_rating = question_rating

            qe.save()

            request.session[notification_to_view_detail_question_key_name] = "Thực hiện tạo đánh giá câu hỏi thành công"
            return redirect(to="practice:view_detail_question", question_id=question.id)

        data_in_params = urlsafe_base64_encode(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        return redirect(to=f"{reverse('practice:process_new_question_evaluation', args=[question_id])}?data={data_in_params}")

    else:
        return HttpResponseNotAllowed(['GET', 'POST'])


@ensure_is_not_anonymous_user
def process_new_comment_evaluation(request, comment_id):
    if request.method == 'GET':
        params = request.GET

        http_code = params.get('http_code')
        if http_code == '404':
            return HttpResponseNotFound(_('<h1>Not Found</h1>'))

        comment = Comment.objects.filter(id=comment_id, state='Normal')
        if not comment:
            return HttpResponseNotFound(_('<h1>Not Found</h1>'))
        comment = comment[0]

        data = {
            'evaluation_content': {'errors': [], 'value': '', 'label': _('Đánh giá mới')},
            'errors': [],
            'previous_adjacent_url': set_prev_adj_url(request),
        }

        data_in_params = params.get('data')
        if data_in_params:
            try:
                data_in_params = json.loads(urlsafe_base64_decode(data_in_params).decode('utf-8'))

                if 'evaluation_content' in data_in_params and isinstance(data_in_params['evaluation_content'], dict):
                    evaluation_content_errors = data_in_params['evaluation_content'].get('errors')
                    if evaluation_content_errors and isinstance(evaluation_content_errors, type(data['evaluation_content']['errors'])):
                        for evaluation_content_error in evaluation_content_errors:
                            data['evaluation_content']['errors'].append(_(evaluation_content_error))
                    evaluation_content_value = data_in_params['evaluation_content'].get('value')
                    if evaluation_content_value and isinstance(evaluation_content_value, type(data['evaluation_content']['value'])):
                        data['evaluation_content']['value'] = evaluation_content_value

                data_errors = data_in_params.get('errors')
                if data_errors and isinstance(data_errors, type(data['errors'])):
                    data['errors'] = data_errors

            except (UnicodeDecodeError, ValueError):
                pass

        context = {
            "suffix_utc": '' if not timezone.get_current_timezone_name() == 'UTC' else 'UTC',
            "comment": comment,
            "data": data,
        }
        return render(request, "practice/new_comment_evaluation.html", context)

    elif request.method == 'POST':
        comment = Comment.objects.filter(id=comment_id, state='Normal')
        if not comment:
            return redirect(to=f"{reverse('practice:process_new_comment_evaluation')}?http_code=404")
        comment = comment[0]

        data = {
            'evaluation_content': {'errors': [], 'value': ''},
            'errors': [],
        }

        params = request.POST
        is_valid = True

        data['evaluation_content']['value'] = params.get('evaluation_content', '')
        evaluation_content = data['evaluation_content']['value'].strip()
        if not evaluation_content:
            is_valid = False
            data['evaluation_content']['errors'].append('Đánh giá phải có thể đọc.')

        if is_valid:
            ce = CommentEvaluation(
                content=evaluation_content,
                comment_id=comment.id,
                user_id=request.user.id,
                created_at=datetime.datetime.now(datetime.timezone.utc),
                updated_at=datetime.datetime.now(datetime.timezone.utc),
            )
            ce.save()

            request.session[notification_to_view_detail_question_key_name] = "Thực hiện tạo đánh giá bình luận thành công"
            return redirect(to="practice:view_detail_question", question_id=comment.question.id)

        data_in_params = urlsafe_base64_encode(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        return redirect(to=f"{reverse('practice:process_new_comment_evaluation', args=[comment_id])}?data={data_in_params}")

    else:
        return HttpResponseNotAllowed(['GET', 'POST'])


# ========================================== Admin ====================================================
@ensure_is_admin
@require_http_methods(['GET'])
def view_pending_questions_by_admin(request):
    return view_questions(request, path_name='practice:view_pending_questions_by_admin', filters=[Q(state='Pending')])


@ensure_is_admin
@require_http_methods(['GET'])
def view_locked_questions_by_admin(request):
    return view_questions(request, path_name='practice:view_locked_questions_by_admin', filters=[Q(state='Locked')])


@ensure_is_admin
@require_http_methods(['GET'])
def view_unapproved_questions_by_admin(request):
    return view_questions(request, path_name='practice:view_unapproved_questions_by_admin', filters=[Q(state='Unapproved')])


@ensure_is_admin
@require_http_methods(['GET'])
def view_approved_questions_by_admin(request):
    return view_questions(request, path_name='practice:view_approved_questions_by_admin', filters=[Q(state='Approved')])


@ensure_is_admin
@require_http_methods(['POST'])
def process_question_by_admin(request, question_id):
    question = Question.objects.filter(id=question_id)
    if not question:
        return redirect(to=f"{reverse('practice:view_detail_question', args=[question_id])}?http_code=404")
    question = question[0]

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
            request.session[notification_to_view_detail_question_key_name] = "Thực hiện duyệt câu hỏi thành công"
            return redirect(to='practice:view_detail_question', question_id=question_id)
        else:
            return redirect(to=f"{reverse('practice:view_detail_question', args=[question_id])}?http_code=400")
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
            request.session[notification_to_view_detail_question_key_name] = "Thực hiện không duyệt câu hỏi thành công"
            return redirect(to='practice:view_detail_question', question_id=question_id)
        else:
            return redirect(to=f"{reverse('practice:view_detail_question', args=[question_id])}?http_code=400")
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
            request.session[notification_to_view_detail_question_key_name] = "Thực hiện ẩn câu hỏi thành công"
            return redirect(to='practice:view_detail_question', question_id=question_id)
        else:
            return redirect(to=f"{reverse('practice:view_detail_question', args=[question_id])}?http_code=400")
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
            request.session[notification_to_view_detail_question_key_name] = "Thực hiện hiện câu hỏi thành công"
            return redirect(to='practice:view_detail_question', question_id=question_id)
        else:
            return redirect(to=f"{reverse('practice:view_detail_question', args=[question_id])}?http_code=400")
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
            request.session[notification_to_view_detail_question_key_name] = "Thực hiện duyệt câu hỏi thành công"
            return redirect(to='practice:view_detail_question', question_id=question_id)
        else:
            return redirect(to=f"{reverse('practice:view_detail_question', args=[question_id])}?http_code=400")
    else:
        return _HttpResponseBadRequest()


def view_evaluations_by_admin(request, path_name=None, filters=None, evaluation_type='question'):
    params = request.GET
    filters_and_sorters_key_name = f'{path_name}__filters_and_sorters'

    filters = filters or []

    if params.get('filter', '') == 'input':
        request.session[filters_and_sorters_key_name] = {
            'filter_by_content': params.get('filter_by_content', ''),
            'filter_by_author_code': params.get('filter_by_author_code', ''),
        }
    elif not request.session.get(filters_and_sorters_key_name):
        request.session[filters_and_sorters_key_name] = {
            'filter_by_content': '',
            'filter_by_author_code': '',
        }

    _filters_and_sorters = request.session[filters_and_sorters_key_name]
    filter_by_content = _filters_and_sorters['filter_by_content']

    if filter_by_content:
        contents = [content.strip() for content in filter_by_content.split(',') if content.strip()]
        if contents:
            filters.append(Q(content__iregex=r"^.*" + ('|'.join(contents)) + r".*$"))

    author_codes = _filters_and_sorters['filter_by_author_code']
    if author_codes:
        author_codes = [author_code.strip() for author_code in author_codes.split(',') if author_code.strip()]
        if author_codes:
            filters.append(Q(user__code__iregex=r"^.*" + ('|'.join(author_codes)) + r".*$"))

    if evaluation_type == 'comment':
        limit, page_offset, page_count, offset = get_limit_offset_count(
            session=request.session,
            limit_in_params=params.get('limit', ''),
            limit_key_name='practice.views.view_evaluations_by_admin__limit',
            offset_in_params=params.get('offset', ''),
            records_count=CommentEvaluation.objects.filter(*filters).distinct().count()
        )

        evaluations = CommentEvaluation.objects.filter(*filters).order_by('-updated_at').distinct()[offset:(offset + limit)]
    else:
        limit, page_offset, page_count, offset = get_limit_offset_count(
            session=request.session,
            limit_in_params=params.get('limit', ''),
            limit_key_name='practice.views.view_evaluations_by_admin__limit',
            offset_in_params=params.get('offset', ''),
            records_count=QuestionEvaluation.objects.filter(*filters).exclude(content='').distinct().count()
        )

        evaluations = QuestionEvaluation.objects.filter(*filters).order_by('-updated_at').exclude(content='').distinct()[offset:(offset + limit)]

    context = {
        "suffix_utc": '' if not timezone.get_current_timezone_name() == 'UTC' else 'UTC',
        "evaluations": evaluations,
        "evaluation_conditions": {
            "page_range": range(1, page_count + 1),
            "limits": [4, 8, 16],
            "path_name": path_name,
            "type": evaluation_type,
            "limit": limit,
            "include_limit_exclude_offset_url": f"{reverse(path_name)}?limit={limit}",
            "page_offset": page_offset,
            'filter_by_content': filter_by_content,
        },
    }
    return render(request, "practice/evaluations.html", context)


@ensure_is_admin
@require_http_methods(['GET'])
def view_unlocked_question_evaluations_by_admin(request):
    return view_evaluations_by_admin(request, path_name='practice:view_unlocked_question_evaluations_by_admin', filters=[~Q(state='Locked')], evaluation_type='question')


@ensure_is_admin
@require_http_methods(['GET'])
def view_unlocked_comment_evaluations_by_admin(request):
    return view_evaluations_by_admin(request, path_name='practice:view_unlocked_comment_evaluations_by_admin', filters=[~Q(state='Locked')], evaluation_type='comment')


@ensure_is_admin
@require_http_methods(['GET'])
def view_locked_question_evaluations_by_admin(request):
    return view_evaluations_by_admin(request, path_name='practice:view_locked_question_evaluations_by_admin', filters=[Q(state='Locked')], evaluation_type='question')


@ensure_is_admin
@require_http_methods(['GET'])
def view_locked_comment_evaluations_by_admin(request):
    return view_evaluations_by_admin(request, path_name='practice:view_locked_comment_evaluations_by_admin', filters=[Q(state='Locked')], evaluation_type='comment')


@ensure_is_admin
def process_evaluation_by_admin(request, evaluation_id):
    if request.method == 'GET':
        params = request.GET

        http_code = params.get('http_code')
        if http_code == '400':
            return HttpResponseBadRequest()
        elif http_code == '404':
            return HttpResponseNotFound(_('<h1>Not Found</h1>'))

        notification = request.session.get(notification_to_process_evaluation_by_admin_key_name, '')
        if notification:
            notification = _(notification)
            request.session[notification_to_process_evaluation_by_admin_key_name] = ''

        question = None
        comment = None
        evaluation_type = params.get('type', 'question')
        if evaluation_type == 'comment':
            evaluation = CommentEvaluation.objects.filter(id=evaluation_id)
            if not evaluation:
                return HttpResponseNotFound(_('<h1>Not Found</h1>'))
            evaluation = evaluation[0]
            comment = evaluation.comment
            question = comment.question
        else:
            evaluation = QuestionEvaluation.objects.filter(id=evaluation_id).exclude(content='')
            if not evaluation:
                return HttpResponseNotFound(_('<h1>Not Found</h1>'))
            evaluation = evaluation[0]
            question = evaluation.question

        data = {
            'previous_adjacent_url': set_prev_adj_url(request),
        }

        context = {
            "suffix_utc": '' if not timezone.get_current_timezone_name() == 'UTC' else 'UTC',
            "notification": notification,
            "evaluation": evaluation,
            "question": question,
            "comment": comment,
            "type": evaluation_type,
            "data": data,
            "question_addition_image": question.get_addition_image(),
            "question_latex_image": question.get_latex_image(),
            "question_video": question.get_video(),
            "question_audio": question.get_audio(),
        }
        return render(request, "practice/detail_evaluation.html", context)

    elif request.method == 'POST':
        params = request.POST

        evaluation_type = params.get('type', 'question')
        if evaluation_type == 'comment':
            evaluation = CommentEvaluation.objects.filter(id=evaluation_id)
            if not evaluation:
                return redirect(to=f"{reverse('practice:process_evaluation_by_admin', args=[evaluation_id])}?type={evaluation_type}&http_code=404")
            evaluation = evaluation[0]
        else:
            evaluation = QuestionEvaluation.objects.filter(id=evaluation_id).exclude(content='')
            if not evaluation:
                return redirect(to=f"{reverse('practice:process_evaluation_by_admin', args=[evaluation_id])}?type={evaluation_type}&http_code=404")
            evaluation = evaluation[0]

        params = request.POST

        # action: 1 : Pending -> Locked
        # action: 2 : Comment: !Locked -> Locked
        # action: 3 : Question: !Locked -> Locked
        if params.get('action', '') == '1':
            if evaluation.state == 'Pending':
                evaluation.state = 'Locked'
                evaluation.updated_at = datetime.datetime.now(datetime.timezone.utc)
                evaluation.save()
                lg = Log(
                    model_name='Evaluation',
                    object_id=evaluation_id,
                    user_id=request.user.id,
                    content="Pending -> Locked",
                    created_at=datetime.datetime.now(datetime.timezone.utc)
                )
                lg.save()
                return redirect(to=f"{reverse('practice:process_evaluation_by_admin', args=[evaluation_id])}?type={evaluation_type}")
            else:
                return redirect(to=f"{reverse('practice:process_evaluation_by_admin', args=[evaluation_id])}?type={evaluation_type}&http_code=400")
        elif params.get('action', '') == '2':
            if evaluation_type == 'comment' and evaluation.state == 'Pending' and evaluation.comment and evaluation.comment.state != 'Locked':
                c = evaluation.comment
                c.state = 'Locked'
                c.updated_at = datetime.datetime.now(datetime.timezone.utc)
                c.save()
                lg = Log(
                    model_name='Comment',
                    object_id=c.id,
                    user_id=request.user.id,
                    content="Not Locked -> Locked",
                    created_at=datetime.datetime.now(datetime.timezone.utc)
                )
                lg.save()
                request.session[notification_to_process_evaluation_by_admin_key_name] = "Thực hiện ẩn bình luận thành công"
                return redirect(to=f"{reverse('practice:process_evaluation_by_admin', args=[evaluation_id])}?type={evaluation_type}")
            else:
                return redirect(to=f"{reverse('practice:process_evaluation_by_admin', args=[evaluation_id])}?type={evaluation_type}&http_code=400")
        elif params.get('action', '') == '3':
            if evaluation_type == 'question' and evaluation.state == 'Pending' and evaluation.question and evaluation.question.state != 'Locked':
                q = evaluation.question
                q.state = 'Locked'
                q.save()
                lg = Log(
                    model_name='Question',
                    object_id=q.id,
                    user_id=request.user.id,
                    content="Not Locked -> Locked",
                    created_at=datetime.datetime.now(datetime.timezone.utc)
                )
                lg.save()
                request.session[notification_to_process_evaluation_by_admin_key_name] = "Thực hiện ẩn câu hỏi thành công"
                return redirect(to=f"{reverse('practice:process_evaluation_by_admin', args=[evaluation_id])}?type={evaluation_type}")
            else:
                return redirect(to=f"{reverse('practice:process_evaluation_by_admin', args=[evaluation_id])}?type={evaluation_type}&http_code=400")
        else:
            return _HttpResponseBadRequest()

    else:
        return HttpResponseNotAllowed(['GET', 'POST'])


def view_comments_by_admin(request, path_name=None, filters=None):
    params = request.GET
    filters_and_sorters_key_name = f'{path_name}__filters_and_sorters'

    filters = filters or []

    if params.get('filter', '') == 'input':
        request.session[filters_and_sorters_key_name] = {
            'filter_by_content': params.get('filter_by_content', ''),
            'filter_by_author_code': params.get('filter_by_author_code', ''),
        }
    elif not request.session.get(filters_and_sorters_key_name):
        request.session[filters_and_sorters_key_name] = {
            'filter_by_content': '',
            'filter_by_author_code': '',
        }

    _filters_and_sorters = request.session[filters_and_sorters_key_name]
    filter_by_content = _filters_and_sorters['filter_by_content']
    filter_by_author_code = _filters_and_sorters['filter_by_author_code']

    if filter_by_content:
        contents = [content.strip() for content in filter_by_content.split(',') if content.strip()]
        if contents:
            filters.append(Q(content__iregex=r"^.*" + ('|'.join(contents)) + r".*$"))

    if filter_by_author_code:
        author_codes = [author_code.strip() for author_code in filter_by_author_code.split(',') if author_code.strip()]
        if author_codes:
            filters.append(Q(user__code__iregex=r"^.*" + ('|'.join(author_codes)) + r".*$"))

    limit, page_offset, page_count, offset = get_limit_offset_count(
        session=request.session,
        limit_in_params=params.get('limit', ''),
        limit_key_name='practice.views.view_comments_by_admin__limit',
        offset_in_params=params.get('offset', ''),
        records_count=Comment.objects.filter(*filters).distinct().count()
    )

    comments = Comment.objects.filter(*filters).order_by('-updated_at').distinct()[offset:(offset + limit)]

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
            'filter_by_author_code': filter_by_author_code,
        },
    }
    return render(request, "practice/comments.html", context)


@ensure_is_admin
@require_http_methods(['GET'])
def view_unlocked_comments_by_admin(request):
    return view_comments_by_admin(request, path_name='practice:view_unlocked_comments_by_admin', filters=[~Q(state='Locked')])


@ensure_is_admin
@require_http_methods(['GET'])
def view_locked_comments_by_admin(request):
    return view_comments_by_admin(request, path_name='practice:view_locked_comments_by_admin', filters=[Q(state='Locked')])


@ensure_is_admin
def process_comment_by_admin(request, comment_id):
    if request.method == 'GET':
        params = request.GET

        http_code = params.get('http_code')
        if http_code == '400':
            return HttpResponseBadRequest()
        elif http_code == '404':
            return HttpResponseNotFound(_('<h1>Not Found</h1>'))

        comment = Comment.objects.filter(id=comment_id)
        if not comment:
            return HttpResponseNotFound(_('<h1>Not Found</h1>'))
        comment = comment[0]

        data = {
            'previous_adjacent_url': set_prev_adj_url(request),
        }

        context = {
            "suffix_utc": '' if not timezone.get_current_timezone_name() == 'UTC' else 'UTC',
            "comment": comment,
            "data": data,
            "question_addition_image": comment.question.get_addition_image(),
            "question_latex_image": comment.question.get_latex_image(),
            "question_video": comment.question.get_video(),
            "question_audio": comment.question.get_audio(),
        }
        return render(request, "practice/detail_comment.html", context)

    elif request.method == 'POST':
        comment = Comment.objects.filter(id=comment_id)
        if not comment:
            return redirect(to=f"{reverse('practice:process_comment_by_admin', args=[comment_id])}?http_code=404")
        comment = comment[0]

        params = request.POST

        # action: 1 : Normal -> Locked
        # action: 2 : Locked -> Normal
        if params.get('action', '') == '1':
            if comment.state == 'Normal':
                comment.state = 'Locked'
                comment.updated_at = datetime.datetime.now(datetime.timezone.utc)
                comment.save()
                lg = Log(
                    model_name='Comment',
                    object_id=comment.id,
                    user_id=request.user.id,
                    content="Normal -> Locked",
                    created_at=datetime.datetime.now(datetime.timezone.utc)
                )
                lg.save()
                return redirect(to='practice:process_comment_by_admin', comment_id=comment_id)
            else:
                return redirect(to=f"{reverse('practice:process_comment_by_admin', args=[comment_id])}?http_code=400")
        elif params.get('action', '') == '2':
            if comment.state == 'Locked':
                comment.state = 'Normal'
                comment.updated_at = datetime.datetime.now(datetime.timezone.utc)
                comment.save()
                lg = Log(
                    model_name='Comment',
                    object_id=comment.id,
                    user_id=request.user.id,
                    content="Locked -> Normal",
                    created_at=datetime.datetime.now(datetime.timezone.utc)
                )
                lg.save()
                return redirect(to='practice:process_comment_by_admin', comment_id=comment_id)
            else:
                return redirect(to=f"{reverse('practice:process_comment_by_admin', args=[comment_id])}?http_code=400")
        else:
            return _HttpResponseBadRequest()

    else:
        return HttpResponseNotAllowed(['GET', 'POST'])


def view_users_by_admin(request, path_name=None, filters=None):
    params = request.GET
    filters_and_sorters_key_name = f'{path_name}__filters_and_sorters'

    filters = filters or []

    if params.get('filter', '') == 'input':
        request.session[filters_and_sorters_key_name] = {
            'filter_by_name': params.get('filter_by_name', ''),
            'filter_by_code': params.get('filter_by_code', ''),
        }
    elif not request.session.get(filters_and_sorters_key_name):
        request.session[filters_and_sorters_key_name] = {
            'filter_by_name': '',
            'filter_by_code': '',
        }

    _filters_and_sorters = request.session[filters_and_sorters_key_name]
    filter_by_name = _filters_and_sorters['filter_by_name']

    if filter_by_name:
        names = [name.strip() for name in filter_by_name.split(',') if name.strip()]
        if names:
            filters.append(Q(name__iregex=r"^.*" + ('|'.join(names)) + r".*$"))

    codes = _filters_and_sorters['filter_by_code']
    if codes:
        codes = [code.strip() for code in codes.split(',') if code.strip()]
        if codes:
            filters.append(Q(code__iregex=r"^.*" + ('|'.join(codes)) + r".*$"))

    limit, page_offset, page_count, offset = get_limit_offset_count(
        session=request.session,
        limit_in_params=params.get('limit', ''),
        limit_key_name='practice.views.view_users_by_admin__limit',
        offset_in_params=params.get('offset', ''),
        records_count=get_user_model().objects.filter(*filters).exclude(role='Admin').distinct().count()
    )

    users = get_user_model().objects.filter(*filters).exclude(role='Admin').order_by('-updated_at').distinct()[offset:(offset + limit)]

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
@require_http_methods(['GET'])
def view_unlocked_users_by_admin(request):
    return view_users_by_admin(request, path_name='practice:view_unlocked_users_by_admin', filters=[~Q(state='Locked')])


@ensure_is_admin
@require_http_methods(['GET'])
def view_locked_users_by_admin(request):
    return view_users_by_admin(request, path_name='practice:view_locked_users_by_admin', filters=[Q(state='Locked')])


@ensure_is_admin
@require_http_methods(['POST'])
def process_user_by_admin(request, user_id):
    user = get_user_model().objects.filter(id=user_id)
    if not user:
        return redirect(to=f"{reverse('practice:process_profile', args=[user_id])}?http_code=404")
    user = user[0]

    # admin can not lock admin
    if user.role == 'Admin':
        return redirect(to=f"{reverse('practice:process_profile', args=[user.id])}?http_code=400")

    params = request.POST

    if params.get('unlock', '') == 'on':
        if user.state == 'Locked':
            user.state = 'Normal'
            user.save()
            lg = Log(
                model_name='User',
                object_id=user.id,
                user_id=request.user.id,
                content="Locked -> Normal",
                created_at=datetime.datetime.now(datetime.timezone.utc)
            )
            lg.save()
            request.session[
                notification_to_process_profile_key_name] = "Thực hiện mở khoá tài khoản người dùng thành công"
            return redirect(to="practice:process_profile", profile_id=user_id)
        else:
            return redirect(to=f"{reverse('practice:process_profile', args=[user.id])}?http_code=400")
    elif params.get('lock', '') == 'on':
        if user.state == 'Normal':
            user.state = 'Locked'
            user.save()
            lg = Log(
                model_name='User',
                object_id=user.id,
                user_id=request.user.id,
                content="Normal -> Locked",
                created_at=datetime.datetime.now(datetime.timezone.utc)
            )
            lg.save()
            # logout all session of this user
            for s in Session.objects.all():
                raw_session = s.get_decoded()
                if raw_session.get('_auth_user_id', 0) == user_id:
                    s.delete()
                    print(raw_session)
            request.session[notification_to_process_profile_key_name] = "Thực hiện khoá tài khoản người dùng thành công"
            return redirect(to="practice:process_profile", profile_id=user_id)
        else:
            return redirect(to=f"{reverse('practice:process_profile', args=[user.id])}?http_code=400")
    else:
        return _HttpResponseBadRequest()


@ensure_is_admin
def process_question_tags_by_admin(request):
    if request.method == 'GET':
        path_name = "practice:process_question_tags_by_admin"
        filters_and_sorters_key_name = f'{path_name}__filters_and_sorters'

        data = {
            'name': {'errors': [], 'value': '', 'label': _('Nhãn câu hỏi mới')},
            'errors': [],
        }

        params = request.GET

        if params.get('filter', '') == 'input':
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

        kfilter = {}
        if filter_by_name:
            names = [name.strip() for name in filter_by_name.split(',') if name.strip()]
            if names:
                kfilter['name__iregex'] = r"^.*" + ('|'.join(names)) + r".*$"

        limit, page_offset, page_count, offset = get_limit_offset_count(
            session=request.session,
            limit_in_params=params.get('limit', ''),
            limit_key_name='',
            offset_in_params=offset_in_params,
            records_count=QuestionTag.objects.filter(**kfilter).distinct().count()
        )

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

                data_errors = data_in_params.get('errors')
                if data_errors and isinstance(data_errors, type(data['errors'])):
                    data['errors'] = data_errors

            except (UnicodeDecodeError, ValueError):
                pass

        question_tags = QuestionTag.objects.filter(**kfilter).order_by('-id').distinct()[offset:(offset + limit)]

        context = {
            "suffix_utc": '' if not timezone.get_current_timezone_name() == 'UTC' else 'UTC',
            "question_tags": question_tags,
            "question_tag_conditions": {
                "page_range": range(1, page_count + 1),
                "limits": [4, 8, 16],
                "path_name": path_name,
                "limit": limit,
                "include_limit_exclude_offset_url": f"{reverse(path_name)}?limit={limit}",
                "page_offset": page_offset,
                'filter_by_name': filter_by_name,
            },
            "data": data,
        }
        return render(request, "practice/question_tags.html", context)

    elif request.method == 'POST':
        data = {
            'name': {'errors': [], 'value': ''},
            'errors': [],
        }

        is_valid = True
        params = request.POST

        data['name']['value'] = params.get('name', '')
        new_name = data['name']['value'].strip()
        if not new_name:
            is_valid = False
            data['name']['errors'].append('Nhãn cần có thể đọc.')
        elif QuestionTag.objects.filter(name=new_name):
            is_valid = False
            data['name']['errors'].append('Nhãn đã tồn tại.')

        if is_valid:
            qt = QuestionTag(name=data['name']['value'].strip())
            qt.save()
            lg = Log(
                model_name='QuestionTag',
                object_id=qt.id,
                user_id=request.user.id,
                content="Create",
                created_at=datetime.datetime.now(datetime.timezone.utc)
            )
            lg.save()

            return redirect(to=f"{reverse('practice:process_question_tags_by_admin')}?limit={params.get('limit', '')}&offset=1")

        data_in_params = urlsafe_base64_encode(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        return redirect(to=f"{reverse('practice:process_question_tags_by_admin')}?limit={params.get('limit', '')}&offset={params.get('offset', '')}&data={data_in_params}")

    else:
        return HttpResponseNotAllowed(['GET', 'POST'])
