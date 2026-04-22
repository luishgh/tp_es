from .common import _configure_time_locale

_configure_time_locale()

from .course_items import (  # noqa: E402,F401
    course_item_delete_view,
    course_item_create_view,
    course_item_detail_view,
    module_create_view,
    publish_course_item_view,
    quiz_delete_view,
    quiz_edit_view,
    submission_review_view,
)
from .admin_views import create_user_view  # noqa: E402,F401
from .auth import login_view, logout_view  # noqa: E402,F401
from .courses import (  # noqa: E402,F401
    course_detail_view,
    course_performance_view,
    courses_hub_view,
    enrollment_decision_view,
    publish_course_view,
    request_enrollment_view,
)
from .calendar import calendar_view  # noqa: E402,F401
from .dashboard import index  # noqa: E402,F401
