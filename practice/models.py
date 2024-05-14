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
    # [{'content': text, 'is_true': bool}]
    choices = models.JSONField(verbose_name=_('Các lựa chọn'), default=list, )

    def upload_to(self, filename):
        # "images/practice/%Y%m%d%H%M%S%f" + removed_#_code + filename
        code = getattr(self.user, 'code', '#')[1:]
        return f"images/practice/{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S%f')}{code}/" + filename

    image = models.ImageField(verbose_name=_('Tên tệp hình ảnh'), upload_to=upload_to, )
    tag = models.ForeignKey(verbose_name=_('Nhãn'), to=QuestionTag, on_delete=models.RESTRICT, )
    user = models.ForeignKey(verbose_name=_('Người dùng'), to=get_user_model(), on_delete=models.CASCADE, )
    # datetime.datetime.now(datetime.timezone.utc)
    created_at = models.DateTimeField(_('Thời điểm tạo'), )

    objects = models.Manager()


class Answer(models.Model):
    # [int, int, ...] lưu số thứ tự của các lựa chọn được chọn
    choices = models.JSONField(verbose_name=_('Các lựa chọn'), default=list)
    is_correct = models.BooleanField(verbose_name=_('Đúng không?'), )
    question = models.ForeignKey(verbose_name=_('Câu hỏi'), to=Question, on_delete=models.CASCADE, )
    user = models.ForeignKey(verbose_name=_('Người dùng'), to=get_user_model(), on_delete=models.CASCADE, )
    # datetime.datetime.now(datetime.timezone.utc)
    created_at = models.DateTimeField(_('Thời điểm tạo'), )

    objects = models.Manager()


class Comment(models.Model):
    STATE_CHOICES = {
        'Normal': _('Bình thường'),
        'Locked': _('Đã khóa'),
    }
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
    content = models.TextField(verbose_name=_('Nội dung đánh giá'), )
    # datetime.datetime.now(datetime.timezone.utc)
    created_at = models.DateTimeField(_('Thời điểm tạo'), )

    objects = models.Manager()


class CommentEvaluation(models.Model):
    comment = models.ForeignKey(verbose_name=_('Bình luận'), to=Comment, on_delete=models.CASCADE, )
    user = models.ForeignKey(verbose_name=_('Người dùng'), to=get_user_model(), on_delete=models.CASCADE, )
    content = models.TextField(verbose_name=_('Nội dung đánh giá'), )
    # datetime.datetime.now(datetime.timezone.utc)
    created_at = models.DateTimeField(_('Thời điểm tạo'), )

    objects = models.Manager()


class QuestionHashTag:
    name = models.CharField(verbose_name=_('Tên hashtag'), max_length=255, )
    questions = models.ManyToManyField(to=Question)

#thêm công thức toán học
#hash tag
#cau hoi nhieu cAU tra loi dung
#lỗi hiển thị sai trên danh sach cau hỏi