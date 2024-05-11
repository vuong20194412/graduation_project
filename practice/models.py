import datetime

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model


# Create your models here.
class QuestionTag(models.Model):
    name = models.CharField(_('Tên nhãn'), max_length=255, )

    objects = models.Manager()


class Question(models.Model):
    STATE_CHOICES = {
        'Pending': _('Chờ duyệt'),
        'Unapproved': _('Không được duyệt'),
        'Approved': _('Đã duyệt'),
        'Locked': _('Đã khóa'),
    }
    title = models.CharField(_('Tiêu đề'), max_length=255, )
    state = models.CharField(verbose_name=_('Trạng thái'), max_length=255, choices=STATE_CHOICES, default='Pending', )
    choices = models.JSONField(verbose_name=_('Các lựa chọn'), default=list, )
    true_choice = models.IntegerField(verbose_name=_('Đáp án là lựa chọn thứ'), )

    def upload_to(self, filename):
        # "images/practice/%Y%m%d%H%M%S%f" + removed_#_code + filename
        code0 = getattr(self.user, 'code')
        code = self.user.code[1:]
        return f"images/practice/{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S%f')}{code}/" + filename

    image = models.ImageField(verbose_name=_('Tên tệp hình ảnh'), upload_to=upload_to, )
    tag = models.ForeignKey(verbose_name=_('Nhãn'), to=QuestionTag, on_delete=models.RESTRICT, )
    user = models.ForeignKey(verbose_name=_('Người dùng'), to=get_user_model(), on_delete=models.CASCADE, )
    # datetime.datetime.now(datetime.timezone.utc)
    created_at = models.DateTimeField(_('Thời điểm tạo'), )

    objects = models.Manager()


class Answer(models.Model):
    choice = models.IntegerField(verbose_name=_('Lựa chọn là lựa chọn thứ'), default=0)
    question = models.ForeignKey(verbose_name=_('Câu hỏi'), to=Question, on_delete=models.CASCADE, )
    user = models.ForeignKey(verbose_name=_('Người dùng'), to=get_user_model(), on_delete=models.CASCADE, )
    # datetime.datetime.now(datetime.timezone.utc)
    created_at = models.DateTimeField(_('Thời điểm tạo'), )

    objects = models.Manager()


class Comment(models.Model):
    content = models.TextField(verbose_name=_('Nội dung'), default='')
    question = models.ForeignKey(verbose_name=_('Câu hỏi'), to=Question, on_delete=models.CASCADE, )
    user = models.ForeignKey(verbose_name=_('Người dùng'), to=get_user_model(), on_delete=models.CASCADE, )
    # datetime.datetime.now(datetime.timezone.utc)
    created_at = models.DateTimeField(_('Thời điểm tạo'), )

    objects = models.Manager()


class Evaluation(models.Model):
    TYPE_CHOICES = {
        'Question evaluation': _('Đánh giá câu hỏi'),
        'Comment evaluation': _('Đánh giá bình luận'),
    }
    type = models.CharField(verbose_name=_('Loại đánh giá'), max_length=255, choices=TYPE_CHOICES, )
    user = models.ForeignKey(verbose_name=_('Người dùng'), to=get_user_model(), on_delete=models.CASCADE, )
    content = models.TextField(verbose_name=_('Nội dung đánh giá'), )
    # datetime.datetime.now(datetime.timezone.utc)
    created_at = models.DateTimeField(_('Thời điểm tạo'), )

    objects = models.Manager()
