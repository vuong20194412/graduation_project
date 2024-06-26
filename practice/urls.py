from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from . import views

app_name = 'practice'
urlpatterns = [
    path('question/tag/admin/', views.process_question_tags_by_admin, name='process_question_tags_by_admin'),

    path('user/admin/<int:user_id>/', views.process_user_by_admin, name='process_user_by_admin'),
    path('user/admin/locked/', views.view_locked_users_by_admin, name='view_locked_users_by_admin'),
    path('user/admin/', views.view_unlocked_users_by_admin, name='view_unlocked_users_by_admin'),

    path('comment/<int:comment_id>/evaluation/new/', views.process_new_comment_evaluation, name='process_new_comment_evaluation'),
    path('comment/admin/<int:comment_id>/', views.process_comment_by_admin, name='process_comment_by_admin'),
    path('comment/admin/hided/', views.view_locked_comments_by_admin, name='view_locked_comments_by_admin'),
    path('comment/admin/', views.view_unlocked_comments_by_admin, name='view_unlocked_comments_by_admin'),

    path('evaluation/<int:evaluation_id>/', views.process_evaluation_by_admin, name='process_evaluation_by_admin'),
    path('evaluation/admin/processed/comment/', views.view_locked_comment_evaluations_by_admin, name='view_locked_comment_evaluations_by_admin'),
    path('evaluation/admin/processed/', views.view_locked_question_evaluations_by_admin, name='view_locked_question_evaluations_by_admin'),
    path('evaluation/admin/comment/', views.view_unlocked_comment_evaluations_by_admin, name='view_unlocked_comment_evaluations_by_admin'),
    path('evaluation/admin/', views.view_unlocked_question_evaluations_by_admin, name='view_unlocked_question_evaluations_by_admin'),

    path('profile/<int:profile_id>/', views.process_profile, name='process_profile'),

    path('answer/<int:answer_id>/', views.view_detail_answer, name='view_detail_answer'),
    path('answer/new/<int:question_id>', views.process_new_answer, name='process_new_answer'),

    path('question/<int:question_id>/evaluation/new/', views.process_new_question_evaluation, name='process_new_question_evaluation'),
    path('question/<int:question_id>/comment/', views.process_comments_in_question, name='process_comments_in_question'),
    path('question/<int:question_id>', views.view_detail_question, name='view_detail_question'),
    path('question/new/', views.process_new_question, name='process_new_question'),
    path('question/admin/<int:question_id>/', views.process_question_by_admin, name='process_question_by_admin'),
    path('question/admin/pending/', views.view_pending_questions_by_admin, name='view_pending_questions_by_admin'),
    path('question/admin/locked/', views.view_locked_questions_by_admin, name='view_locked_questions_by_admin'),
    path('question/admin/unapproved/', views.view_unapproved_questions_by_admin, name='view_unapproved_questions_by_admin'),
    path('question/admin/approved/', views.view_approved_questions_by_admin, name='view_approved_questions_by_admin'),

    path('question/created/', views.view_created_questions, name='view_created_questions'),
    path('question/answered/', views.view_answered_questions, name='view_answered_questions'),
    path('question/unanswered', views.view_unanswered_questions, name='view_unanswered_questions'),

    path('', views.view_root, name='view_root'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
