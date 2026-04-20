import locale

from ..models import UserProfile


def _configure_time_locale():
    for locale_name in ('pt_BR.UTF-8', 'pt_BR.utf8', 'Portuguese_Brazil.1252'):
        try:
            locale.setlocale(locale.LC_TIME, locale_name)
            return
        except locale.Error:
            continue


def _user_role(user):
    profile = getattr(user, 'profile', None)
    return getattr(profile, 'role', UserProfile.Role.STUDENT)
