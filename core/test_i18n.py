from django.conf import settings
from django.template.loader import get_template
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from core.models import Announcement


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class LanguageTests(TestCase):
    def test_russian_default_even_with_english_browser_or_cookie(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'en'
        response = self.client.get('/', HTTP_ACCEPT_LANGUAGE='en')
        self.assertContains(response, '<html lang="ru">')
        self.assertContains(response, 'Лаборатория химии высоких энергий')
        self.assertEqual(response.headers['Content-Language'], 'ru')

    def test_english_interface_and_untranslated_database_content(self):
        Announcement.objects.create(title='Объявление из базы', text='Исходный текст', is_published=True)
        response = self.client.get('/en/')
        self.assertContains(response, '<html lang="en">')
        self.assertContains(response, 'Laboratory of High Energy Chemistry')
        self.assertContains(response, 'For students')
        self.assertContains(response, 'Объявление из базы')
        self.assertContains(response, 'href="/en/science/"')
        self.assertEqual(response.headers['Content-Language'], 'en')

    def test_language_switch_preserves_page_and_query_in_both_directions(self):
        response = self.client.post('/i18n/setlang/', {
            'language': 'en', 'next': '/gallery/?page=2',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/en/gallery/?page=2')
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, 'en')
        response = self.client.post('/en/i18n/setlang/', {
            'language': 'ru', 'next': '/en/gallery/?page=2',
        })
        self.assertEqual(response.url, '/gallery/?page=2')

    def test_switch_rejects_external_redirect_and_requires_csrf(self):
        response = self.client.post('/i18n/setlang/', {
            'language': 'en', 'next': 'https://example.com/',
        })
        self.assertEqual(response.url, '/en/')
        self.assertEqual(Client(enforce_csrf_checks=True).post(
            '/i18n/setlang/', {'language': 'en'},
        ).status_code, 403)

    def test_public_pages_and_login_render_in_english(self):
        names = ['core:home', 'core:science', 'core:gallery', 'core:contacts',
                 'core:history', 'core:news', 'users:people', 'users:login',
                 'education:students', 'publications:publications', 'research:projects']
        with translation.override('en'):
            for name in names:
                with self.subTest(page=name):
                    response = self.client.get(reverse(name))
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, '<html lang="en">')
            response = self.client.get(reverse('users:login'))
        self.assertContains(response, 'Username')
        self.assertContains(response, 'Password')
        self.assertContains(response, 'Staff sign-in')

    def test_shared_pagination_is_translated(self):
        from django.core.paginator import Paginator
        page = Paginator(range(3), 1).page(2)
        from django.contrib.auth.models import AnonymousUser
        request = RequestFactory().get('/en/gallery/')
        request.user = AnonymousUser()
        with translation.override('en'):
            html = get_template('core/components/pagination.html').render(
                {'page_obj': page}, request=request,
            )
        self.assertIn('Page 2 of 3', html)
        self.assertIn('Next', html)

    def test_all_public_templates_compile(self):
        for app in ('core', 'users', 'education', 'research', 'publications'):
            for path in (settings.BASE_DIR / app / 'templates' / app).rglob('*.html'):
                with self.subTest(template=str(path)):
                    get_template(str(path.relative_to(settings.BASE_DIR / app / 'templates')))
