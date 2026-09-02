from .roles import get_user_role


def current_user_role(request):
    role = get_user_role(request.user)
    return {
        'current_user_role': role,
        'current_user_role_label': role.label if role is not None else None,
    }
