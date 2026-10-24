# SPDX-License-Identifier: MPL-2.0
import os
from django.core.wsgi import get_wsgi_application
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "railet.settings")
application = get_wsgi_application()
