# SPDX-License-Identifier: MPL-2.0
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class AddressMigrationTests(TransactionTestCase):
    def test_existing_customer_and_history_survive_with_unknown_address(self):
        executor=MigrationExecutor(connection)
        try:
            old=[('customers','0001_initial')]
            executor.migrate(old)
            apps=executor.loader.project_state(old).apps
            dealer=apps.get_model('core','Dealership').objects.create(name='Synthetic address migration')
            customer=apps.get_model('customers','Customer').objects.create(dealership=dealer,first_name='Migration',last_name='Demo',phone='3055550100',revision=3)
            actor=get_user_model().objects.create_user('address-migration-actor')
            original={'fields':{'first_name':'Migration'},'revision':3}
            event=apps.get_model('customers','CustomerEvent').objects.create(customer=customer,actor_id=actor.pk,changes=original)
            executor=MigrationExecutor(connection);leaves=executor.loader.graph.leaf_nodes();executor.migrate(leaves)
            updated=executor.loader.project_state(leaves).apps
            migrated=updated.get_model('customers','Customer').objects.get(pk=customer.pk)
            self.assertEqual((migrated.first_name,migrated.phone,migrated.revision),('Migration','3055550100',3))
            for name in ('address_line1','address_line2','city','region','postal_code','country'):
                self.assertEqual(getattr(migrated,name),'')
            self.assertEqual(updated.get_model('customers','CustomerEvent').objects.get(pk=event.pk).changes,original)
        finally:
            executor=MigrationExecutor(connection);executor.migrate(executor.loader.graph.leaf_nodes())
