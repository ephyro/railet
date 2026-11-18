# SPDX-License-Identifier: MPL-2.0
from decimal import Decimal
from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


@skipUnless(connection.vendor == 'postgresql', 'Immutable journal fixtures require PostgreSQL truncate teardown')
class AskingPriceMigrationTests(TransactionTestCase):
    def test_existing_costs_and_tasks_survive_with_unknown_asking_price(self):
        executor=MigrationExecutor(connection)
        try:
            old=[('inventory','0006_vehicle_cost_guards')]
            executor.migrate(old)
            apps=executor.loader.project_state(old).apps
            dealer=apps.get_model('core','Dealership').objects.create(name='Synthetic price migration')
            actor=get_user_model().objects.create_user('price-migration-staff')
            apps.get_model('core','Membership').objects.create(user_id=actor.pk,dealership=dealer,role='staff')
            vehicle=apps.get_model('inventory','Vehicle').objects.create(dealership=dealer,stock_number='MIGRATE-PRICE',year=2021,make='Synthetic',model='Migration',acquisition_cost=Decimal('5000.10'),recon_cost=Decimal('100.20'),revision=4)
            task=apps.get_model('inventory','ReconTask').objects.create(vehicle=vehicle,title='Preserve this work',created_by_id=actor.pk)
            entry=apps.get_model('inventory','VehicleCostEntry').objects.create(vehicle=vehicle,kind='cost',category='repair',description='Retained synthetic cost',amount_cents=25035,effective_on=timezone.localdate(),actor_id=actor.pk,task=task)
            executor=MigrationExecutor(connection);leaves=executor.loader.graph.leaf_nodes();executor.migrate(leaves)
            updated=executor.loader.project_state(leaves).apps
            migrated=updated.get_model('inventory','Vehicle').objects.get(pk=vehicle.pk)
            self.assertIsNone(migrated.asking_price)
            self.assertEqual((migrated.acquisition_cost,migrated.recon_cost,migrated.revision),(Decimal('5000.10'),Decimal('100.20'),4))
            self.assertEqual(updated.get_model('inventory','VehicleCostEntry').objects.get(pk=entry.pk).amount_cents,25035)
            self.assertEqual(updated.get_model('inventory','ReconTask').objects.get(pk=task.pk).title,'Preserve this work')
        finally:
            executor=MigrationExecutor(connection);executor.migrate(executor.loader.graph.leaf_nodes())
