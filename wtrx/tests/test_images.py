from unittest.mock import MagicMock

from django.test import TestCase

from ..images import CustomImage


class TestObjectPositionStyle(TestCase):
    """Tests for CustomImage.object_position_style property."""

    def _make_image(self, width, height, focal_point=None):
        """
        Return a CustomImage instance with controlled width, height,
        and focal-point behaviour — without hitting the database.
        """
        image = CustomImage.__new__(CustomImage)
        image.width = width
        image.height = height
        if focal_point is None:
            image.has_focal_point = lambda: False
            image.get_focal_point = lambda: None
        else:
            centroid_x, centroid_y = focal_point
            image.has_focal_point = lambda: True
            fp = MagicMock()
            fp.centroid_x = centroid_x
            fp.centroid_y = centroid_y
            image.get_focal_point = lambda: fp
        return image

    def test_no_focal_point_returns_center(self):
        """When no focal point is set, returns the center fallback."""
        image = self._make_image(800, 600)
        self.assertEqual(image.object_position_style, "object-position: center center;")

    def test_focal_point_center(self):
        """Focal point at exact center of the image → 50% 50%."""
        image = self._make_image(800, 600, focal_point=(400, 300))
        self.assertEqual(image.object_position_style, "object-position: 50% 50%;")

    def test_focal_point_top_left(self):
        """Focal point at origin → 0% 0%."""
        image = self._make_image(800, 600, focal_point=(0, 0))
        self.assertEqual(image.object_position_style, "object-position: 0% 0%;")

    def test_focal_point_bottom_right(self):
        """Focal point at full extent → 100% 100%."""
        image = self._make_image(800, 600, focal_point=(800, 600))
        self.assertEqual(image.object_position_style, "object-position: 100% 100%;")

    def test_focal_point_top_right(self):
        """Focal point at top-right corner → 100% 0%."""
        image = self._make_image(800, 600, focal_point=(800, 0))
        self.assertEqual(image.object_position_style, "object-position: 100% 0%;")

    def test_focal_point_arbitrary_position(self):
        """Focal point at a known off-centre position is calculated correctly."""
        # x = round(200 / 800 * 100) = 25, y = round(150 / 600 * 100) = 25
        image = self._make_image(800, 600, focal_point=(200, 150))
        self.assertEqual(image.object_position_style, "object-position: 25% 25%;")

    def test_focal_point_rounding(self):
        """Percentages are rounded to the nearest integer."""
        # x = round(1 / 3 * 100) = round(33.33) = 33
        # y = round(2 / 3 * 100) = round(66.67) = 67
        image = self._make_image(300, 300, focal_point=(100, 200))
        self.assertEqual(image.object_position_style, "object-position: 33% 67%;")

    def test_has_focal_point_but_zero_width_returns_center(self):
        """If width is 0 (falsy), the focal point cannot be used — falls back to center."""
        image = self._make_image(0, 600, focal_point=(0, 300))
        self.assertEqual(image.object_position_style, "object-position: center center;")

    def test_has_focal_point_but_zero_height_returns_center(self):
        """If height is 0 (falsy), the focal point cannot be used — falls back to center."""
        image = self._make_image(800, 0, focal_point=(400, 0))
        self.assertEqual(image.object_position_style, "object-position: center center;")

    def test_return_value_is_valid_css_declaration(self):
        """Return value always starts with 'object-position:' and ends with ';'."""
        for fp in [None, (400, 300)]:
            image = self._make_image(800, 600, focal_point=fp)
            result = image.object_position_style
            self.assertTrue(result.startswith("object-position:"), result)
            self.assertTrue(result.endswith(";"), result)
