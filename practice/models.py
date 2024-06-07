import datetime
import random

from django.db import models, connections
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.db.models import QuerySet


# def explain(self):
#     cursor = connections[self.db].cursor()
#     query, params = self.query.sql_with_params()
#     cursor.execute('explain %s' % query, params)
#     return '\n'.join(r[0] for r in cursor.fetchall())


#type.__setattr__(QuerySet, 'explain', explain)


# Create your models here.
class QuestionTag(models.Model):
    name = models.CharField(_('tên nhãn câu hỏi'), max_length=255, unique=True)

    objects = models.Manager()


class Question(models.Model):
    STATE_CHOICES = (
        ('Pending', _('Chờ duyệt')),
        ('Unapproved', _('Không được duyệt')),
        ('Approved', _('Đã duyệt')),
        ('Locked', _('Đã ẩn'))
    )
    content = models.TextField(_('nội dung câu hỏi'), default='')
    state = models.CharField(verbose_name=_('trạng thái câu hỏi'), max_length=255, choices=STATE_CHOICES, default='Pending', )
    # [{'content': text, 'is_true': bool}]
    choices = models.JSONField(verbose_name=_('các lựa chọn'), default=list, )

    tag = models.ForeignKey(verbose_name=_('nhãn câu hỏi'), to=QuestionTag, on_delete=models.RESTRICT, )
    user = models.ForeignKey(verbose_name=_('người tạo'), to=get_user_model(), on_delete=models.CASCADE, )
    hashtags = models.TextField(verbose_name=_('các hashtag'), default='')
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
        return f'#{(self.hashtags or "").replace(",", " #")}'

    def get_number_of_answers(self):
        return self.answer_set.count()

    def get_number_of_comments(self):
        return self.comment_set.count()

    def get_latex_image(self):
        if self.id:
            image = QuestionImage.objects.filter(question_id=self.id, name='question_latex_image')
            if image:
                return image[0].image
        return None

    def get_addition_image(self):
        if self.id:
            image = QuestionImage.objects.filter(question_id=self.id, name='question_addition_image')
            if image:
                return image[0].image
        return None


class QuestionImage(models.Model):
    name = models.CharField(_('tên mục đích ảnh'), max_length=255)
    question = models.ForeignKey(verbose_name=_('nhãn câu hỏi'), to=Question, on_delete=models.RESTRICT, null=False)

    def upload_to(self, filename):
        question = self.question
        qid = question.id
        code = question.user.code[1:]
        now = self.created_at
        return f"images/practice/{now.strftime('%Y%m%d%H')}/{code}/{now.strftime('%M%S%f')}{qid}_" + filename

    image = models.ImageField(verbose_name=_('tên tệp hình ảnh'), upload_to=upload_to, )
    # datetime.datetime.now(datetime.timezone.utc)
    created_at = models.DateTimeField(_('thời điểm tạo'), )

    objects = models.Manager()


class Answer(models.Model):
    # [int, int, ...] lưu số thứ tự của các lựa chọn được chọn
    choices = models.JSONField(verbose_name=_('Các lựa chọn'), default=list)
    is_correct = models.BooleanField(verbose_name=_('Đúng không?'), default=False)
    question = models.ForeignKey(verbose_name=_('Câu hỏi'), to=Question, on_delete=models.CASCADE, )
    user = models.ForeignKey(verbose_name=_('Người dùng'), to=get_user_model(), on_delete=models.CASCADE, )
    # datetime.datetime.now(datetime.timezone.utc)
    created_at = models.DateTimeField(_('Thời điểm tạo'), )

    objects = models.Manager()


class Comment(models.Model):
    STATE_CHOICES = (
        ('Normal', _('Bình thường')),
        ('Locked', _('Đã ẩn'))
    )
    content = models.TextField(verbose_name=_('Nội dung'), default='')
    state = models.CharField(verbose_name=_('Trạng thái'), max_length=255, choices=STATE_CHOICES, default='Normal', )
    question = models.ForeignKey(verbose_name=_('Câu hỏi'), to=Question, on_delete=models.CASCADE, )
    user = models.ForeignKey(verbose_name=_('Người dùng'), to=get_user_model(), on_delete=models.CASCADE, )
    # datetime.datetime.now(datetime.timezone.utc)
    created_at = models.DateTimeField(_('Thời điểm tạo'), )
    updated_at = models.DateTimeField(_('Thời điểm cập nhật gần nhất'), )

    objects = models.Manager()


class Evaluation(models.Model):
    question = models.ForeignKey(verbose_name=_('Câu hỏi'), to=Question, on_delete=models.CASCADE, )
    comment = models.ForeignKey(verbose_name=_('Bình luận'), to=Comment, on_delete=models.CASCADE, null=True)
    user = models.ForeignKey(verbose_name=_('Người dùng'), to=get_user_model(), on_delete=models.CASCADE, )
    content = models.TextField(verbose_name=_('Nội dung đánh giá'), default='')
    STATE_CHOICES = (
        ('Pending', _('Chở xử lý')),
        ('Locked', _('Đã xử lý'))
    )
    state = models.CharField(verbose_name=_('Trạng thái'), max_length=255, choices=STATE_CHOICES, default='Pending', )
    # datetime.datetime.now(datetime.timezone.utc)
    created_at = models.DateTimeField(_('Thời điểm tạo'), )
    updated_at = models.DateTimeField(_('Thời điểm cập nhật gần nhất'), )

    objects = models.Manager()

#thêm công thức toán học
#lỗi hiển thị sai trên danh sach cau hỏi