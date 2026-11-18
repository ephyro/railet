# SPDX-License-Identifier: MPL-2.0
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from core.models import Dealership, Membership
from .forms import CustomerForm
from .models import Customer, CustomerEvent
from .services import require_locked_editor, save_customer


class CustomerSaveAuthorizationTests(TestCase):
    def setUp(self):
        self.dealer = Dealership.objects.create(name='Synthetic customer save dealer')
        self.other = Dealership.objects.create(name='Synthetic other customer dealer')
        self.user = get_user_model().objects.create_user('synthetic-customer-editor')
        self.member = Membership.objects.create(user=self.user, dealership=self.dealer, role='staff')
        self.customer = Customer.objects.create(dealership=self.dealer, first_name='Synthetic', last_name='Buyer')
        self.client.force_login(self.user)

    def form(self, editing):
        data = {'first_name': 'Synthetic updated' if editing else 'Synthetic new', 'last_name': 'Buyer', 'revision': '1'}
        form = CustomerForm(data, instance=Customer.objects.get(pk=self.customer.pk) if editing else Customer(dealership=self.dealer), dealership=self.dealer)
        self.assertTrue(form.is_valid(), form.errors)
        return form

    def test_direct_helper_rechecks_revoked_membership_and_activity(self):
        for editing in (False, True):
            for revoked in ('inactive', 'viewer', 'foreign', 'removed'):
                with self.subTest(editing=editing, revoked=revoked):
                    form = self.form(editing)
                    if revoked == 'inactive':
                        get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
                    elif revoked == 'viewer':
                        Membership.objects.filter(pk=self.member.pk).update(role='viewer')
                    elif revoked == 'foreign':
                        Membership.objects.filter(pk=self.member.pk).update(dealership=self.other)
                    else:
                        Membership.objects.filter(pk=self.member.pk).delete()
                    with self.assertRaises(PermissionDenied):
                        save_customer(form, actor=self.user, dealership=self.dealer)
                    self.customer.refresh_from_db()
                    self.assertEqual((Customer.objects.count(), CustomerEvent.objects.count(), self.customer.first_name, self.customer.revision), (1, 0, 'Synthetic', 1))
                    get_user_model().objects.filter(pk=self.user.pk).update(is_active=True)
                    self.member, _ = Membership.objects.update_or_create(user=self.user, defaults={'dealership': self.dealer, 'role': 'staff'})

    def test_direct_helper_rejects_stale_edit(self):
        form = self.form(True)
        Customer.objects.filter(pk=self.customer.pk).update(first_name='Newer synthetic', revision=2)
        with self.assertRaises(ValidationError):
            save_customer(form, actor=self.user, dealership=self.dealer)
        self.customer.refresh_from_db()
        self.assertEqual((self.customer.first_name, self.customer.revision, CustomerEvent.objects.count()), ('Newer synthetic', 2, 0))

    def test_editor_rechecks_before_stale_or_invalid_posts(self):
        for url, data in ((reverse('customer_create'), {'first_name': 'New', 'last_name': 'Buyer'}),
                          (reverse('customer_edit', args=[self.customer.pk]), {'first_name': 'Edited', 'last_name': 'Buyer', 'revision': 1}),
                          (reverse('customer_edit', args=[self.customer.pk]), {'first_name': '', 'last_name': '', 'revision': 1})):
            with self.subTest(url=url, data=data):
                def revoke(user, dealership_id):
                    get_user_model().objects.filter(pk=user.pk).update(is_active=False)
                    return require_locked_editor(user, dealership_id)
                with patch('customers.views.require_locked_editor', side_effect=revoke):
                    self.assertEqual(self.client.post(url, data).status_code, 403)
                self.assertEqual((Customer.objects.count(), CustomerEvent.objects.count()), (1, 0))
