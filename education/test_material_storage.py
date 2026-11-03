import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from .models import TeachingMaterial


class MaterialStorageTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        settings = override_settings(
            MEDIA_ROOT=self.root / 'public',
            PRIVATE_PUBLICATIONS_ROOT=self.root / 'private',
        )
        settings.enable()
        self.addCleanup(settings.disable)

    def material(self, **kwargs):
        return TeachingMaterial.objects.create(
            title='Document', file=SimpleUploadedFile('guide.pdf', b'document'), **kwargs,
        )

    def test_storage_and_download_permissions(self):
        material = self.material()
        self.assertTrue(Path(material.file.path).is_relative_to(self.root / 'private'))
        self.assertFalse((self.root / 'public' / material.file.name).exists())
        self.assertEqual(material.file.url, material.get_download_url())
        response = self.client.get(material.get_download_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'document')
        material.access_level = TeachingMaterial.AccessLevel.INTERNAL
        material.save()
        self.assertEqual(self.client.get(material.get_download_url()).status_code, 403)
        user = get_user_model().objects.create_superuser('admin', password='test')
        self.client.force_login(user)
        response = self.client.get(material.get_download_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'document')
        material.is_published = False
        material.save()
        self.assertEqual(self.client.get(material.get_download_url()).status_code, 404)

    def test_missing_file_returns_404(self):
        material = self.material()
        Path(material.file.path).unlink()
        self.assertEqual(self.client.get(material.get_download_url()).status_code, 404)
