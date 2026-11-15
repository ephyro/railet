# SPDX-License-Identifier: MPL-2.0
from django.db import migrations


def forwards(apps, editor):
    if editor.connection.vendor != 'sqlite':
        return
    for operation in ('UPDATE', 'DELETE'):
        editor.execute(f"CREATE TRIGGER IF NOT EXISTS demo_account_context_{operation.lower()} BEFORE {operation} ON finance_demoaccountcontext BEGIN SELECT RAISE(ABORT, 'Saved account context is immutable'); END")
    editor.execute("""CREATE TRIGGER IF NOT EXISTS demo_account_context_check BEFORE INSERT ON finance_demoaccountcontext WHEN NOT EXISTS (
    SELECT 1 FROM finance_demobook b JOIN deals_draftdeal d ON d.id=NEW.deal_id
    JOIN customers_customer c ON c.id=b.customer_id JOIN inventory_vehicle v ON v.id=d.vehicle_id
    JOIN core_membership m ON m.user_id=NEW.created_by_id AND m.dealership_id=b.dealership_id
    WHERE b.id=NEW.book_id AND d.dealership_id=b.dealership_id AND d.buyer_id=b.customer_id
    AND c.dealership_id=b.dealership_id AND v.dealership_id=b.dealership_id
    AND d.deal_type='bhph' AND d.archived_at IS NULL AND m.role IN ('owner','staff'))
    BEGIN SELECT RAISE(ABORT, 'An authorized matching BHPH draft is required'); END""")


def backwards(apps, editor):
    if editor.connection.vendor == 'sqlite':
        # Leave immutable-row guards in place; remove the cross-table check so
        # older SQLite inventory migrations can rebuild the vehicle table.
        editor.execute('DROP TRIGGER IF EXISTS demo_account_context_check')


class Migration(migrations.Migration):
    dependencies = [('finance', '0013_payment_method'), ('inventory', '0007_vehicle_asking_price_and_more')]
    operations = [migrations.RunPython(forwards, backwards)]
