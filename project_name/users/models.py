from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """
    Custom user model.

    This model exists as an empty subclass of AbstractUser so that future
    projects can add user fields (e.g. profile info, preferences) without
    needing to migrate away from Django's built-in auth.User — which requires
    wiping the database if done after the first migration.

    Even if this project never adds custom fields, the model must be declared
    here from day one. AUTH_USER_MODEL in base.py points to this model.

    Extend this class to add project-specific user fields.
    """

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
