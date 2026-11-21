from django.contrib import admin
from django.urls import reverse
from ninja import Router, Schema

router = Router(tags=["users"])


class AccountProfile(Schema):
    name: str
    email: str
    profession: str
    admin_url: str | None


@router.get("/me", response=AccountProfile)
def get_account_profile(request):
    """Identidad activa y acceso al panel de administración de Django."""
    user = request.user
    return AccountProfile(
        name=user.name,
        email=user.email,
        profession=user.profession,
        admin_url=reverse("admin:index") if admin.site.has_permission(request) else None,
    )
