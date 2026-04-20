from .common import _configure_time_locale

_configure_time_locale()

from .activities import (  # noqa: E402,F401
    activity_create_view,
    module_create_view,
    publish_activity_view,
    resource_detail_view,
    submission_list_view,
)
from .admin_views import create_user_view  # noqa: E402,F401
from .auth import login_view, logout_view  # noqa: E402,F401
from .courses import (  # noqa: E402,F401
    course_detail_view,
    courses_hub_view,
    enrollment_decision_view,
    publish_course_view,
    request_enrollment_view,
)
from .dashboard import calendar_view, index  # noqa: E402,F401
