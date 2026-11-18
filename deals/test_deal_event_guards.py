# SPDX-License-Identifier: MPL-2.0
from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from core.models import Dealership
from inventory.models import Vehicle
from customers.models import Customer
from .models import DraftDeal, DealEvent


def seed():
    dealer = Dealership.objects.create(name='Synthetic deal audit dealer')
    actor = get_user_model().objects.create_user('synthetic-deal-auditor')
    vehicle = Vehicle.objects.create(dealership=dealer, stock_number='SYN-DEAL', year=2020,
        make='Synthetic', model='Car')
    buyer = Customer.objects.create(dealership=dealer, first_name='Synthetic', last_name='Buyer')
    deal = DraftDeal.objects.create(dealership=dealer, vehicle=vehicle, buyer=buyer)
    return deal, actor, DealEvent.objects.create(deal=deal, actor=actor, snapshot={'revision': 1, 'action': 'draft_saved'})


def assert_guards(case, event):
    original = DealEvent.objects.filter(pk=event.pk).values().get()
    for sql in ("UPDATE deals_dealevent SET snapshot = '{}' WHERE id = %s",
                'DELETE FROM deals_dealevent WHERE id = %s'):
        with case.assertRaisesMessage(DatabaseError, 'Deal events are immutable'):
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql, [event.pk])
        case.assertEqual(DealEvent.objects.filter(pk=event.pk).values().get(), original)


class DealEventGuardTests(TestCase):
    def test_append_allowed_mutation_rejected_and_fields_preserved(self):
        deal, actor, event = seed()
        assert_guards(self, event)
        next_event = DealEvent.objects.create(deal=deal, actor=actor, snapshot={'revision': 2})
        assert_guards(self, next_event)
        self.assertEqual(deal.events.count(), 2)


class DealEventMigrationTests(TransactionTestCase):
    def test_existing_history_preserved_and_reverse_reapply(self):
        latest = MigrationExecutor(connection).loader.graph.leaf_nodes()
        try:
            MigrationExecutor(connection).migrate([('deals', '0016_followup_event_immutable')])
            _, _, event = seed()
            baseline = DealEvent.objects.values().get(pk=event.pk)
            MigrationExecutor(connection).migrate([('deals', '0017_deal_event_immutable')])
            self.assertEqual(DealEvent.objects.values().get(pk=event.pk), baseline)
            assert_guards(self, event)
            MigrationExecutor(connection).migrate([('deals', '0016_followup_event_immutable')])
            DealEvent.objects.filter(pk=event.pk).update(snapshot={'changed': True})
            DealEvent.objects.filter(pk=event.pk).delete()
            self.assertFalse(DealEvent.objects.filter(pk=event.pk).exists())
            MigrationExecutor(connection).migrate([('deals', '0017_deal_event_immutable')])
            _, _, new_event = self.append_event()
            assert_guards(self, new_event)
        finally:
            # SQLite's test flush uses DELETE, so remove this test's events only
            # while the reversible guard is absent, then restore the schema.
            MigrationExecutor(connection).migrate([('deals', '0016_followup_event_immutable')])
            DealEvent.objects.all().delete()
            MigrationExecutor(connection).migrate(latest)

    def append_event(self):
        deal = DraftDeal.objects.get()
        actor = get_user_model().objects.get(username='synthetic-deal-auditor')
        return deal, actor, DealEvent.objects.create(deal=deal, actor=actor, snapshot={'revision': 2})
