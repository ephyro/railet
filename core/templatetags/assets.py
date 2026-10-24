# SPDX-License-Identifier: MPL-2.0
"""Content-version local assets so live development never mixes old CSS with new HTML."""
from hashlib import sha256
from pathlib import Path
from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()

@register.simple_tag
def asset_url(name):
    url = static(name)
    path = finders.find(name)
    if path:
        version = sha256(Path(path).read_bytes()).hexdigest()[:12]
        return f"{url}?v={version}"
    return url
