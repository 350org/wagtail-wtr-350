from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class UserModelTests(TestCase):
    def test_create_user(self):
        """Can create a basic user via the custom User model."""
        user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )
        self.assertEqual(user.username, "testuser")
        self.assertEqual(user.email, "test@example.com")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_create_superuser(self):
        """Can create a superuser via the custom User model."""
        user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass123",
        )
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_user_str(self):
        """User string representation is the username."""
        user = User.objects.create_user(username="alice", password="alicepass123")
        self.assertEqual(str(user), "alice")

    def test_custom_model_is_active(self):
        """AUTH_USER_MODEL points to the custom User model with correct app_label."""
        self.assertEqual(User.__name__, "User")
        self.assertTrue(User._meta.app_label.endswith("_users"))
