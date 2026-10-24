# SPDX-License-Identifier: MPL-2.0
import os
import sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "railet.settings")
from django.core.management import execute_from_command_line
execute_from_command_line(sys.argv)
