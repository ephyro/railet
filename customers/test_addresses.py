# SPDX-License-Identifier: MPL-2.0
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from core.models import Dealership,Membership
from .models import Customer,CustomerEvent,ADDRESS_FIELDS
from .forms import CustomerForm


class CustomerAddressTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer=Dealership.objects.create(name='Synthetic address dealer')
        cls.other=Dealership.objects.create(name='Other address dealer')
        cls.users={}
        for name,role,dealer in [('staff','staff',cls.dealer),('viewer','viewer',cls.dealer),('foreign','owner',cls.other)]:
            user=get_user_model().objects.create_user('address-'+name);cls.users[name]=user
            Membership.objects.create(user=user,dealership=dealer,role=role)
        cls.customer=Customer.objects.create(dealership=cls.dealer,first_name='Riley',last_name='Demo')

    def setUp(self):
        self.client.force_login(self.users['staff']);self.url=reverse('customer_edit',args=[self.customer.pk])
        self.address={'address_line1':'123 Synthetic Lane','address_line2':'Suite 4','city':'Demo City','region':'FL','postal_code':'00000','country':'United States'}

    def post(self,**changes):
        self.customer.refresh_from_db()
        data={'first_name':self.customer.first_name,'last_name':self.customer.last_name,'phone':self.customer.phone,'email':self.customer.email,'revision':self.customer.revision}
        data.update(changes);return self.client.post(self.url,data)

    def test_optional_fields_start_unknown_and_quick_creation_needs_only_name(self):
        response=self.client.get(reverse('customer_create'))
        self.assertFalse(response.context['form'].address_open)
        for name in ADDRESS_FIELDS:self.assertFalse(response.context['form'][name].value())
        self.assertEqual(self.client.post(reverse('customer_create'),{'first_name':'Alex','last_name':'Synthetic'}).status_code,302)
        self.assertEqual(Customer.objects.get(first_name='Alex').address_lines,())

    def test_address_saved_once_displayed_and_audited(self):
        self.assertEqual(self.post(**self.address).status_code,302)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.address_lines,('123 Synthetic Lane','Suite 4','Demo City, FL 00000','United States'))
        event=CustomerEvent.objects.get()
        for name,value in self.address.items():self.assertEqual(event.changes['fields'][name],value)
        self.assertEqual(event.changes['revision'],2)
        response=self.client.get(reverse('customer_detail',args=[self.customer.pk]))
        self.assertContains(response,'123 Synthetic Lane')
        self.assertTrue(self.client.get(self.url).context['form'].address_open)

    def test_omitted_fields_preserve_address_and_explicit_blank_clears(self):
        self.post(**self.address)
        self.assertEqual(self.post(phone='3055550100').status_code,302)
        self.customer.refresh_from_db();self.assertEqual(self.customer.address_line1,self.address['address_line1'])
        self.post(address_line1='')
        self.customer.refresh_from_db();self.assertEqual(self.customer.address_line1,'');self.assertEqual(self.customer.city,'Demo City')

    def test_invalid_input_keeps_fields_and_opens_address_section(self):
        response=self.post(**{**self.address,'address_line1':'x'*161})
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.context['form'].address_open)
        self.assertEqual(response.context['form']['city'].value(),'Demo City')
        self.customer.refresh_from_db();self.assertEqual(self.customer.address_line1,'')
        self.assertFalse(CustomerEvent.objects.exists())

    def test_newlines_rejected_and_unicode_international_address_preserved(self):
        self.assertTrue(self.post(address_line1='First\nSecond').context['form'].errors)
        international={'address_line1':'42 Rue Démonstration','city':'Montréal','region':'Québec','postal_code':'H0H 0H0','country':'Canada'}
        self.assertEqual(self.post(**international).status_code,302)
        self.customer.refresh_from_db();self.assertEqual(self.customer.city,'Montréal')
        self.assertEqual(self.customer.postal_code,'H0H 0H0')

    def test_stale_form_cannot_overwrite_address(self):
        self.post(**self.address)
        response=self.post(address_line1='Stale synthetic street',revision=1)
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.context['form']['address_line1'].value(),'Stale synthetic street')
        self.customer.refresh_from_db();self.assertEqual(self.customer.address_line1,self.address['address_line1'])

    def test_viewer_foreign_scope_and_escaping(self):
        self.post(address_line1='<script>synthetic</script>')
        response=self.client.get(reverse('customer_detail',args=[self.customer.pk]))
        self.assertContains(response,'&lt;script&gt;synthetic&lt;/script&gt;')
        self.assertNotContains(response,'<script>synthetic</script>')
        self.client.force_login(self.users['viewer']);self.assertEqual(self.post(**self.address).status_code,403)
        self.client.force_login(self.users['foreign']);self.assertEqual(self.client.get(self.url).status_code,404)

    def test_prefixed_and_keyword_bound_older_forms_preserve_address(self):
        self.post(**self.address);self.customer.refresh_from_db()
        data={'new-first_name':'Riley','new-last_name':'Demo','new-revision':self.customer.revision}
        form=CustomerForm(data=data,prefix='new',instance=self.customer,dealership=self.dealer)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.cleaned_data['address_line1'],self.address['address_line1'])
        self.assertEqual(form['address_line1'].field.widget.attrs['autocomplete'],'address-line1')
