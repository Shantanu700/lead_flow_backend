from django.contrib.auth.models import AbstractUser
from django.db import models

from base.manager import UserManager
from base.model import ModelBase


class User(ModelBase, AbstractUser):
    USER_MODEL_FIELDS = ModelBase.BASE_MODEL_FIELDS + (
        "is_superuser",
        "last_login",
        "is_staff",
        "is_active",
        "date_joined",
        "groups",
        "user_permissions",
    )

    name = models.CharField(max_length=255, blank=True)
    # Login identifier; always stored lowercase by UserManager / RegisterSerializer.
    email = models.EmailField(unique=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]
