from django.contrib.auth.models import BaseUserManager
from django.db.models import Manager

from base.enums import Status

# Write your managers here


class DeleteStatusManager(Manager):
    def get_queryset(self):
        return super().get_queryset().exclude(status=Status.DELETED)


class UserManager(DeleteStatusManager, BaseUserManager):
    r"""Email-login manager for the custom User.

    Email is the login (`USERNAME_FIELD`), stored lowercase so uniqueness and
    login are case-insensitive. `username` is kept for the stock admin and
    mirrors the email.
    """

    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        extra_fields.setdefault("username", email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)
