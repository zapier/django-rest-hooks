#!/usr/bin/env python

import sys
import django
from django.conf import settings


APP_NAME = 'rest_hooks'
if django.VERSION < (1, 8):
    comments = 'django.contrib.comments'
else:
    comments = 'django_comments'

settings.configure(
    DEBUG=True,
    DATABASES={
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
        }
    },
    USE_TZ=True,
    ROOT_URLCONF='{0}.tests'.format(APP_NAME),
    MIDDLEWARE_CLASSES=(
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
    ),
    SITE_ID=1,
    HOOK_EVENTS={},
    HOOK_THREADING=False,
    INSTALLED_APPS=(
        'django.contrib.auth',
        'django.contrib.contenttypes',
        'django.contrib.sessions',
        'django.contrib.admin',
        'django.contrib.sites',
        comments,
        APP_NAME,
    ),
)

from django.test.utils import get_runner

if hasattr(django, 'setup'):
    django.setup()
TestRunner = get_runner(settings)
test_runner = TestRunner()
failures = test_runner.run_tests([APP_NAME])
if failures:
    sys.exit(failures)
