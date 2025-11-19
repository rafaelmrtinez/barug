"""
WSGI config for barug project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "barug.settings")

# Ensure Django apps are loaded before wiring application containers which import models.
# Call get_wsgi_application() first so AppRegistry is ready, then import containers.
application = get_wsgi_application()

from barug.containers import app