"""Centralized Staff location scoping (R-007, D-005)."""

from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404

from core.models import KostLocation


class NoLocation(Exception):
    """Raised when a user has neither global Owner access nor an assigned location."""


def location_for(user: AbstractBaseUser | AnonymousUser) -> KostLocation | None:
    """Return None for Owner (all locations), KostLocation for Staff, or raise NoLocation."""
    if not user.is_authenticated:
        raise NoLocation("Unauthenticated user has no location access.")
    if getattr(user, "is_superuser", False):
        return None
    if not getattr(user, "is_staff", False):
        raise NoLocation("Non-staff user has no location access.")
    try:
        profile: Any = getattr(user, "admin_profile", None)
    except ObjectDoesNotExist as exc:
        raise NoLocation("Staff user has no admin profile.") from exc
    location: KostLocation | None = (
        getattr(profile, "assigned_location", None) if profile is not None else None
    )
    if location is None:
        raise NoLocation("Staff user has no assigned location.")
    return location


def scoped[T: models.Model](
    qs: QuerySet[T], user: AbstractBaseUser | AnonymousUser, path: str
) -> QuerySet[T]:
    """Filter queryset to user's location via lookup `path`, or return empty queryset."""
    try:
        location = location_for(user)
    except NoLocation:
        return qs.none()
    if location is None:
        return qs
    target: KostLocation | int = location.pk if path in ("pk", "id") else location
    return qs.filter(**{path: target})


def get_scoped_or_404[T: models.Model](
    qs: QuerySet[T], user: AbstractBaseUser | AnonymousUser, path: str, **lookup: Any
) -> T:
    """Fetch a single object within user's location scope, or raise Http404."""
    return get_object_or_404(scoped(qs, user, path).distinct(), **lookup)
