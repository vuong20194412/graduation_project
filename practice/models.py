import datetime

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model


# Create your models here.
class QuestionTag(models.Model):
    name = models.CharField(_('tên nhãn câu hỏi'), max_length=255, )

    objects = models.Manager()


class Question(models.Model):
    STATE_CHOICES = (
        ('Pending', _('Chờ duyệt')),
        ('Unapproved', _('Không được duyệt')),
        ('Approved', _('Đã duyệt')),
        ('Locked', _('Đã khóa'))
    )
    content = models.TextField(_('nội dung câu hỏi'), default='')
    state = models.CharField(verbose_name=_('trạng thái câu hỏi'), max_length=255, choices=STATE_CHOICES, default='Pending', )
    # [{'content': text, 'is_true': bool}]
    choices = models.JSONField(verbose_name=_('các lựa chọn'), default=list, )

    def upload_to(self, filename):
        # "images/practice/%Y%m%d%H%M%S%f" + removed_#_code + filename
        code = getattr(self.user, 'code', '#')[1:]
        return f"images/practice/{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S%f')}{code}/" + filename

    image = models.ImageField(verbose_name=_('tên tệp hình ảnh'), upload_to=upload_to, )
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

    objects = models.Manager()


class QuestionEvaluation(models.Model):
    question = models.ForeignKey(verbose_name=_('Câu hỏi'), to=Question, on_delete=models.CASCADE, )
    user = models.ForeignKey(verbose_name=_('Người dùng'), to=get_user_model(), on_delete=models.CASCADE, )
    content = models.TextField(verbose_name=_('Nội dung đánh giá'), default='')
    STATE_CHOICES = (
        ('Pending', _('Chở xử lý')),
        ('Locked', _('Đã xử lý'))
    )
    state = models.CharField(verbose_name=_('Trạng thái'), max_length=255, choices=STATE_CHOICES, default='Pending', )
    # datetime.datetime.now(datetime.timezone.utc)
    created_at = models.DateTimeField(_('Thời điểm tạo'), )

    objects = models.Manager()


class CommentEvaluation(models.Model):
    comment = models.ForeignKey(verbose_name=_('Bình luận'), to=Comment, on_delete=models.CASCADE, )
    user = models.ForeignKey(verbose_name=_('Người dùng'), to=get_user_model(), on_delete=models.CASCADE, )
    content = models.TextField(verbose_name=_('Nội dung đánh giá'), default='')
    STATE_CHOICES = (
        ('Pending', _('Chở xử lý')),
        ('Locked', _('Đã xử lý'))
    )
    state = models.CharField(verbose_name=_('Trạng thái'), max_length=255, choices=STATE_CHOICES, default='Pending', )
    # datetime.datetime.now(datetime.timezone.utc)
    created_at = models.DateTimeField(_('Thời điểm tạo'), )

    objects = models.Manager()

#thêm công thức toán học
#lỗi hiển thị sai trên danh sach cau hỏi