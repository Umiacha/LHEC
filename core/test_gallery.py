from io import BytesIO
from tempfile import TemporaryDirectory
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .gallery import validate_gallery_image
from .models import GalleryPhoto


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class GalleryTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        settings = override_settings(MEDIA_ROOT=directory.name)
        settings.enable()
        self.addCleanup(settings.disable)

    def upload(self, name='photo.png', size=(1200, 800)):
        output = BytesIO()
        Image.new('RGB', size, 'red').save(output, 'PNG')
        return SimpleUploadedFile(name, output.getvalue(), content_type='image/png')

    def photo(self, **kwargs):
        return GalleryPhoto.objects.create(
            image=self.upload(), year=1985, caption='Архивный снимок', **kwargs,
        )

    def test_archive_path_and_thumbnail(self):
        photo = self.photo()
        self.assertTrue(photo.image.name.startswith('gallery/1985/'))
        self.assertTrue(photo.thumbnail.name.startswith('gallery/1985/thumbnails/'))
        with Image.open(photo.thumbnail.path) as preview:
            self.assertEqual(preview.size, (960, 640))
            self.assertEqual(preview.format, 'JPEG')
        original = photo.image.name
        thumbnail = photo.thumbnail.name
        photo.year = 1986
        photo.save()
        self.assertEqual(photo.image.name, original)
        self.assertEqual(photo.thumbnail.name, thumbnail)

    def test_replacement_and_bulk_deletion_clean_files(self):
        photo = self.photo()
        old_paths = [photo.image.path, photo.thumbnail.path]
        photo.image = self.upload()
        photo.year = 1990
        with self.captureOnCommitCallbacks(execute=True):
            photo.save()
        self.assertTrue(photo.image.name.startswith('gallery/1990/'))
        self.assertTrue(all(not Path(path).exists() for path in old_paths))
        paths = [photo.image.path, photo.thumbnail.path]
        with self.captureOnCommitCallbacks(execute=True):
            GalleryPhoto.objects.all().delete()
        self.assertTrue(all(not Path(path).exists() for path in paths))

    def test_public_page_hides_drafts_and_escapes_caption(self):
        hidden = self.photo()
        public = self.photo(is_published=True)
        public.caption = '<script>alert(1)</script>'
        public.save()
        response = self.client.get(reverse('core:gallery'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['page_obj']), [public])
        self.assertContains(response, public.thumbnail.url)
        self.assertContains(response, public.image.url)
        self.assertNotContains(response, hidden.image.url)
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, '<script>')

    def test_pagination_and_empty_state(self):
        response = self.client.get(reverse('core:gallery'))
        self.assertContains(response, 'Фотографии скоро появятся.')
        photo = self.photo(is_published=True)
        # Reuse the files to exercise pagination without generating 24 more images.
        GalleryPhoto.objects.bulk_create([
            GalleryPhoto(image=photo.image.name, thumbnail=photo.thumbnail.name,
                         caption=f'Фото {i}', year=1985, is_published=True)
            for i in range(24)
        ])
        response = self.client.get(reverse('core:gallery'), {'page': 2})
        self.assertEqual(len(response.context['page_obj']), 1)
        self.assertContains(response, 'Страница 2 из 2')

    def test_rejects_invalid_and_oversized_uploads(self):
        with self.assertRaises(ValidationError):
            validate_gallery_image(SimpleUploadedFile('bad.jpg', b'not an image'))
        oversized = self.upload()
        oversized.size = 21 * 1024 * 1024
        with self.assertRaises(ValidationError):
            validate_gallery_image(oversized)
