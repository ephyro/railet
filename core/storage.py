# SPDX-License-Identifier: MPL-2.0
from django.core.files.storage import FileSystemStorage


class PrivateMediaStorage(FileSystemStorage):
    """Files can only be reached through an authorized application download."""

    def url(self, name):
        raise ValueError("Private files require an authenticated application URL.")
