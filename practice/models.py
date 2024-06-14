import os.path
import pathlib
import random

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Max, F, Q, Subquery
from django.utils.translation import gettext_lazy as _


# def explain(self):
#     cursor = connections[self.db].cursor()
#     query, params = self.query.sql_with_params()
#     cursor.execute('explain %s' % query, params)
#     return '\n'.join(r[0] for r in cursor.fetchall())


# type.__setattr__(QuerySet, 'explain', explain)


# Create your models here.
class QuestionTag(models.Model):
    name = models.CharField(_('tên nhãn câu hỏi'), max_length=255, unique=True)

    objects = models.Manager()


class Question(models.Model):
    content = models.TextField(_('nội dung câu hỏi'), default='', )
    STATE_CHOICES = (
        ('Pending', _('Chờ duyệt')),
        ('Unapproved', _('Không được duyệt')),
        ('Approved', _('Đã duyệt')),
        ('Locked', _('Đã ẩn'))
    )
    state = models.CharField(verbose_name=_('trạng thái câu hỏi'), max_length=255, choices=STATE_CHOICES, default='Pending', )
    # [{'content': text, 'is_true': bool}]
    choices = models.JSONField(verbose_name=_('các lựa chọn'), default=list, )

    tag = models.ForeignKey(verbose_name=_('nhãn câu hỏi'), to=QuestionTag, on_delete=models.RESTRICT, )
    user = models.ForeignKey(verbose_name=_('người tạo'), to=get_user_model(), on_delete=models.CASCADE, )
    hashtags = models.TextField(verbose_name=_('các hashtag'), default='', )
    # datetime.datetime.now(datetime.timezone.utc)
    created_at = models.DateTimeField(_('thời điểm tạo'), )

    objects = models.Manager()

    def is_single_choice(self):
        count = 0
        for choice in self.choices:
            if choice['is_true']:
                count += 1
                if count > 1:
                    return False
        return True

    def get_display_hashtags(self):
        return f'#{(self.hashtags or "").replace(",", " #")}' if self.hashtags else ''

    def get_number_of_answers(self):
        return self.answer_set.count()

    def get_number_of_comments(self):
        return self.comment_set.count()

    def get_latex_image(self):
        if self.id:
            qm = QuestionMedia.objects.filter(question_id=self.id, name='question_latex_image', media_type='image')
            if qm:
                return qm[0].file
        return None

    def get_addition_image(self):
        if self.id:
            qm = QuestionMedia.objects.filter(question_id=self.id, name='question_addition_image', media_type='image')
            if qm:
                return qm[0].file
        return None

    def get_video(self):
        if self.id:
            qm = QuestionMedia.objects.filter(question_id=self.id, name='question_video', media_type='video')
            if qm:
                return qm[0].file
        return None

    def get_audio(self):
        if self.id:
            qm = QuestionMedia.objects.filter(question_id=self.id, name='question_audio', media_type='audio')
            if qm:
                return qm[0].file
        return None

    def get_rating(self):
        user_ids = QuestionEvaluation.objects.filter(question_id=self.id, question_rating__isnull=False).values_list('user_id', flat=True).distinct()
        latest_evaluation_ids = [
            Subquery(QuestionEvaluation.objects.filter(question_id=self.id, question_rating__isnull=False, user_id=user_id).order_by('-created_at').annotate(latest=Max('created_at')).order_by('-latest').values_list('id', flat=True)) for user_id in user_ids
        ]
        qes = QuestionEvaluation.objects.filter(id__in=latest_evaluation_ids)
        if qes:
            sum_start = 0
            for qe in qes:
                sum_start += qe.question_rating
            return sum_start / len(qes), len(qes)
        return 0, 0


class QuestionMedia(models.Model):
    name = models.CharField(_('tên mục đích media'), max_length=255, )
    question = models.ForeignKey(verbose_name=_('nhãn câu hỏi'), to=Question, on_delete=models.RESTRICT, )
    STATE_CHOICES = (
        ('image', _('Hình ảnh')),
        ('video', _('Video')),
        ('audio', _('Audio')),
    )
    media_type = models.CharField(verbose_name=_('tên loại media'), max_length=255, choices=STATE_CHOICES, default='image', )

    def upload_to(self, filename):
        media_type = self.media_type
        now = self.created_at
        salt = f"{random.randrange(1, 999999)}_"
        prefix = f"{media_type}s/practice/{now.strftime('%Y%m%d%H')}/{now.strftime('%M%S%f')}"
        media_pathname = pathlib.Path(settings.MEDIA_ROOT, prefix + salt + filename)
        while os.path.exists(media_pathname):
            salt = f"{random.randrange(1, 999999)}_"
            media_pathname = pathlib.Path(settings.MEDIA_ROOT, prefix + salt + filename)
        return prefix + salt + filename

    MAX_IMAGE_SIZE = 2.4
    MAX_VIDEO_SIZE = 12
    MAX_AUDIO_SIZE = 1.2
    file = models.FileField(verbose_name=_('tên tệp media'), upload_to=upload_to, unique=True)
    # datetime.datetime.now(datetime.timezone.utc)
    created_at = models.DateTimeField(_('thời điểm tạo'), )

    objects = models.Manager()


class Answer(models.Model):
    # [int, int, ...] lưu số thứ tự của các lựa chọn được chọn
    choices = models.JSONField(verbose_name=_('các lựa chọn'), default=list, )
    is_correct = models.BooleanField(verbose_name=_('đúng không?'), default=False, )
    question = models.ForeignKey(verbose_name=_('câu hỏi'), to=Question, on_delete=models.CASCADE, )
    user = models.ForeignKey(verbose_name=_('người dùng'), to=get_user_model(), on_delete=models.CASCADE, )
    # datetime.datetime.now(datetime.timezone.utc)
    created_at = models.DateTimeField(_('thời điểm tạo'), )

    objects = models.Manager()


class Comment(models.Model):
    content = models.TextField(verbose_name=_('nội dung'), default='', )
    STATE_CHOICES = (
        ('Normal', _('Bình thường')),
        ('Locked', _('Đã ẩn'))
    )
    state = models.CharField(verbose_name=_('trạng thái'), max_length=255, choices=STATE_CHOICES, default='Normal', )
    question = models.ForeignKey(verbose_name=_('câu hỏi'), to=Question, on_delete=models.CASCADE, )
    user = models.ForeignKey(verbose_name=_('người dùng'), to=get_user_model(), on_delete=models.CASCADE, )
    # datetime.datetime.now(datetime.timezone.utc)
    created_at = models.DateTimeField(_('thời điểm tạo'), )
    updated_at = models.DateTimeField(_('thời điểm cập nhật gần nhất'), )

    objects = models.Manager()


class QuestionEvaluation(models.Model):
    question = models.ForeignKey(verbose_name=_('câu hỏi'), to=Question, on_delete=models.CASCADE, )
    QUESTION_RATING_CHOICES = (
        (1, _('1 sao')),
        (2, _('2 sao')),
        (3, _('3 sao')),
        (4, _('4 sao')),
        (5, _('5 sao'))
    )
    question_rating = models.IntegerField(verbose_name=_('số sao cho câu hỏi'), choices=QUESTION_RATING_CHOICES, null=True, )
    user = models.ForeignKey(verbose_name=_('người dùng'), to=get_user_model(), on_delete=models.CASCADE, )
    content = models.TextField(verbose_name=_('nội dung đánh giá'), default='', )
    STATE_CHOICES = (
        ('Pending', _('Chở xử lý')),
        ('Locked', _('Đã xử lý'))
    )
    state = models.CharField(verbose_name=_('trạng thái'), max_length=255, choices=STATE_CHOICES, default='Pending', )
    # datetime.datetime.now(datetime.timezone.utc)
    created_at = models.DateTimeField(_('thời điểm tạo'), )
    updated_at = models.DateTimeField(_('thời điểm cập nhật gần nhất'), )

    objects = models.Manager()


class CommentEvaluation(models.Model):
    comment = models.ForeignKey(verbose_name=_('bình luận'), to=Comment, on_delete=models.CASCADE, )
    user = models.ForeignKey(verbose_name=_('người dùng'), to=get_user_model(), on_delete=models.CASCADE, )
    content = models.TextField(verbose_name=_('nội dung đánh giá'), default='', )
    STATE_CHOICES = (
        ('Pending', _('Chở xử lý')),
        ('Locked', _('Đã xử lý'))
    )
    state = models.CharField(verbose_name=_('trạng thái'), max_length=255, choices=STATE_CHOICES, default='Pending', )
    # datetime.datetime.now(datetime.timezone.utc)
    created_at = models.DateTimeField(_('thời điểm tạo'), )
    updated_at = models.DateTimeField(_('thời điểm cập nhật gần nhất'), )

    objects = models.Manager()


class Log(models.Model):
    model_name = models.CharField(verbose_name=_('tên lớp đối tượng'), max_length=255, )
    object_id = models.IntegerField(verbose_name=_('id đối tượng'), )
    user_id = models.IntegerField(verbose_name=_('id người thực hiện'), )
    content = models.TextField(verbose_name=_('nội dung thay đổi'), default='', )
    created_at = models.DateTimeField(_('thời điểm tạo'), )

    objects = models.Manager()
