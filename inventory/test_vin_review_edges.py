# SPDX-License-Identifier: MPL-2.0
"""Independent overseer regression cases for changing duplicate evidence."""
from django.test import TestCase
from core.models import AuditEvent
from . import test_vin_duplicates as scenarios
from .models import Vehicle


class DuplicateVinEvidenceTests(TestCase):
    def setUp(self):
        scenarios.DuplicateVinReviewTests.setUp(self)

    vehicle = scenarios.DuplicateVinReviewTests.vehicle
    post_create = scenarios.DuplicateVinReviewTests.post_create

    def test_rechecks_changed_matches_and_excludes_forged_foreign_ids(self):
        first = self.vehicle(stock='FIRST', vin='RECHECK')
        initial = self.post_create(vin='recheck')
        self.assertEqual(initial.status_code, 200)
        second = self.vehicle(stock='SECOND', vin=' RECHECK ', status='sold')
        foreign = self.vehicle(stock='PRIVATE', vin='RECHECK', dealership=self.other_dealer)
        response = self.post_create(vin='recheck', duplicate_review_acknowledged='on',
            duplicate_review_reason='Synthetic reviewed reacquisition', duplicate_ids=str(foreign.pk))
        self.assertEqual(response.status_code, 302)
        event = AuditEvent.objects.get(vehicle__stock_number='NEW-STOCK')
        self.assertEqual(event.changes['duplicate_vin_review']['after']['matched_vehicle_ids'], [first.pk, second.pk])
        self.assertNotIn(foreign.pk, event.changes['duplicate_vin_review']['after']['matched_vehicle_ids'])

    def test_disappeared_match_does_not_keep_old_override_metadata(self):
        original = self.vehicle(stock='ORIGINAL', vin='OLD-EVIDENCE')
        self.assertEqual(self.post_create(vin='old-evidence').status_code, 200)
        Vehicle.objects.filter(pk=original.pk).update(vin='CORRECTED')
        response = self.post_create(vin='old-evidence', duplicate_review_acknowledged='on',
            duplicate_review_reason='Old evidence was corrected')
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('duplicate_vin_review', AuditEvent.objects.get(vehicle__stock_number='NEW-STOCK').changes)

    def test_whitespace_only_reason_cannot_bypass_review(self):
        self.vehicle(stock='MATCH', vin='REASON-REQUIRED')
        response = self.post_create(vin='reason-required', duplicate_review_acknowledged='on',
                                    duplicate_review_reason=' \t\n ')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vehicle.objects.filter(stock_number='NEW-STOCK').exists())
        self.assertFalse(AuditEvent.objects.exists())
