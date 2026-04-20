from django.contrib import admin

from .models import (
    Answer,
    AssignmentItem,
    Course,
    CourseItem,
    Enrollment,
    ForumItem,
    ForumMessage,
    Module,
    QuizItem,
    QuizOption,
    QuizQuestion,
    ResourceItem,
    Submission,
    UserProfile,
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'academic_id')
    list_filter = ('role',)
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'academic_id')


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('code', 'title', 'teacher', 'is_published', 'updated_at')
    list_filter = ('is_published',)
    search_fields = ('code', 'title', 'teacher__username')


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'order')
    list_filter = ('course',)
    search_fields = ('title', 'course__code', 'course__title')


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'course', 'status', 'enrolled_at', 'final_grade')
    list_filter = ('status',)
    search_fields = ('student__username', 'course__code', 'course__title')


@admin.register(CourseItem)
class CourseItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'module', 'kind_label', 'is_published')
    list_filter = ('is_published', 'course', 'module')
    search_fields = ('title', 'course__code', 'course__title', 'module__title')


@admin.register(ResourceItem)
class ResourceItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'module', 'is_published')
    list_filter = ('is_published', 'course', 'module')


@admin.register(AssignmentItem)
class AssignmentItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'module', 'due_date', 'max_score', 'is_published')
    list_filter = ('is_published', 'course', 'module')


@admin.register(QuizItem)
class QuizItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'module', 'due_date', 'is_published')
    list_filter = ('is_published', 'course', 'module')


@admin.register(ForumItem)
class ForumItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'module', 'is_published')
    list_filter = ('is_published', 'course', 'module')


@admin.register(QuizQuestion)
class QuizQuestionAdmin(admin.ModelAdmin):
    list_display = ('quiz', 'order', 'weight')
    list_filter = ('quiz__course',)


@admin.register(QuizOption)
class QuizOptionAdmin(admin.ModelAdmin):
    list_display = ('question', 'order', 'is_correct')
    list_filter = ('question__quiz__course',)


@admin.register(ForumMessage)
class ForumMessageAdmin(admin.ModelAdmin):
    list_display = ('forum', 'author', 'created_at')
    list_filter = ('forum__course',)


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('assignment', 'student', 'status', 'score', 'submitted_at', 'graded_at')
    list_filter = ('status', 'assignment__course')
    search_fields = ('student__username', 'assignment__title', 'assignment__course__code')


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ('quiz', 'question', 'student', 'answered_at')
    list_filter = ('quiz__course',)
