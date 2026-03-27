from django.contrib import admin

from .models import Activity, Course, Enrollment, Module, Submission, UserProfile


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


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'course', 'status', 'enrolled_at', 'final_grade')
    list_filter = ('status',)
    search_fields = ('student__username', 'course__code', 'course__title')


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'order')
    list_filter = ('course',)
    search_fields = ('title', 'course__code', 'course__title')


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'activity_type', 'due_date', 'is_published')
    list_filter = ('activity_type', 'is_published', 'course')
    search_fields = ('title', 'course__code', 'course__title')


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('activity', 'student', 'status', 'score', 'submitted_at', 'graded_at')
    list_filter = ('status', 'activity__course')
    search_fields = ('student__username', 'activity__title', 'activity__course__code')
