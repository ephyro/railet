# SPDX-License-Identifier: MPL-2.0
import getpass
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import Dealership, Membership, AuditEvent
from inventory.models import Vehicle
class Command(BaseCommand):
    help = "Create synthetic inventory and a local demo owner. Prompts for a password."
    def add_arguments(self, parser):
        parser.add_argument("--username", default="demo")
        parser.add_argument("--password-file", help="Read a development password from a private file instead of a terminal prompt.")
    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo seeding is only permitted in development mode.")
        User = get_user_model()
        if User.objects.filter(username=options["username"]).exists():
            raise CommandError("Username already exists; choose another. Existing accounts are never changed.")
        if options["password_file"]:
            password_path = Path(options["password_file"])
            if password_path.stat().st_mode & 0o077:
                raise CommandError("Password file must not be accessible to group or other users.")
            password = password_path.read_text().rstrip("\r\n")
        else:
            password = getpass.getpass("Choose demo password (at least 12 characters): ")
        if len(password) < 12:
            raise CommandError("Use at least 12 characters.")
        dealer = Dealership.objects.create(name="Demo Motor Co. — synthetic")
        user = User.objects.create_user(username=options["username"], password=password)
        Membership.objects.create(user=user, dealership=dealer, role=Membership.Role.OWNER)
        for i, (year, make, model, status, brand, title, cost, recon) in enumerate([
            (2021, "Toyota", "Camry SE", "available", "unbranded", True, "14500.00", "475.00"),
            (2019, "Ford", "F-150 XLT", "recon", "rebuilt", False, "11200.00", "1260.00"),
            (2020, "Honda", "Civic Sport", "acquired", "unknown", False, "9800.00", "0.00"),
            (2018, "Mazda", "CX-5 Touring", "available", "unbranded", True, "10750.00", "350.00"),
        ], 1):
            vehicle = Vehicle.objects.create(dealership=dealer, stock_number=f"DEMO-{i:03}", year=year, make=make, model=model, status=status, title_brand=brand, title_received=title, acquisition_cost=cost, recon_cost=recon, notes="Synthetic demonstration vehicle. Not for sale.")
            AuditEvent.objects.create(dealership=dealer, actor=user, vehicle=vehicle, action="demo seeded", changes={})
        self.stdout.write(self.style.SUCCESS("Created demo owner and four synthetic vehicles."))
