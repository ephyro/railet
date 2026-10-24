# SPDX-License-Identifier: MPL-2.0
from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "documents"
    verbose_name = "Supporting files"
