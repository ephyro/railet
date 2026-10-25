# SPDX-License-Identifier: MPL-2.0
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.test import TestCase,Client,override_settings
from django.urls import reverse
from django.utils import timezone
from core.models import Dealership,Membership
from customers.models import Customer
from .models import DemoBook,DemoPosting


@override_settings(DEMO_LEDGER_ENABLED=True)
class LedgerViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer=Dealership.objects.create(name='Synthetic ledger UI')
        cls.other=Dealership.objects.create(name='Other dealer')
        cls.users={}
        for name,role,dealer in [('staff','staff',cls.dealer),('viewer','viewer',cls.dealer),('foreign','owner',cls.other)]:
            user=get_user_model().objects.create_user(name);cls.users[name]=user
            Membership.objects.create(user=user,dealership=dealer,role=role)
        cls.customer=Customer.objects.create(dealership=cls.dealer,first_name='Riley',last_name='Demo')

    def setUp(self):
        self.client.force_login(self.users['staff'])
        self.data={'customer':self.customer.pk,'label':'DEMO synthetic UI account','amount':'10000.25','effective_on':timezone.localdate().isoformat(),'reference':'Synthetic opening provenance','request_key':str(uuid4()),'synthetic_confirmed':'on'}

    def confirm(self,token,**extra):return self.client.post(reverse('ledger_demo_confirm'),{'preview_token':token,'action':'post',**extra})

    def open(self):
        preview=self.client.post(reverse('ledger_demo_new'),self.data)
        self.assertEqual(preview.status_code,200)
        token=preview.context['token'];self.confirm(token)
        return DemoBook.objects.get(),token

    def test_preview_does_not_post_and_retry_is_safe(self):
        preview=self.client.post(reverse('ledger_demo_new'),self.data)
        self.assertEqual(DemoBook.objects.count(),0)
        self.assertContains(preview,'Nothing has been posted')
        first=self.confirm(preview.context['token'],amount='1')
        second=self.confirm(preview.context['token'])
        self.assertEqual(first.url,second.url)
        self.assertEqual(DemoBook.objects.count(),1);self.assertEqual(DemoPosting.objects.get().amount_cents,1000025)

    def test_manual_receipt_and_correction_effects_are_explicit(self):
        book,_=self.open()
        data={key:self.data[key] for key in ('effective_on','reference','synthetic_confirmed')}
        data.update(amount='125.50',request_key=str(uuid4()))
        preview=self.client.post(reverse('ledger_demo_receipt',args=[book.pk]),data)
        self.assertContains(preview,'Principal does not decrease')
        self.confirm(preview.context['token'])
        entry=book.postings.get(kind='receipt')
        correction=self.client.post(reverse('ledger_demo_reverse',args=[book.pk,entry.pk]),{**data,'reference':'Synthetic correction','request_key':str(uuid4())})
        self.assertContains(correction,'$125.50')
        self.assertNotContains(correction,'name="amount"')
        self.confirm(correction.context['token'])
        response=self.client.get(reverse('ledger_demo_detail',args=[book.pk]))
        self.assertContains(response,'$10,000.25');self.assertContains(response,'Balanced, one opening entry')
        self.assertEqual(book.postings.count(),3)

    def test_edit_preview_preserves_work_and_sensitive_text_is_escaped(self):
        preview=self.client.post(reverse('ledger_demo_new'),{**self.data,'reference':'<script>synthetic</script>'})
        self.assertContains(preview,'&lt;script&gt;')
        edit=self.confirm(preview.context['token'],action='edit')
        self.assertEqual(edit.context['form']['reference'].value(),'<script>synthetic</script>')
        self.assertEqual(DemoBook.objects.count(),0)

    def test_consent_invalid_amount_and_dates_prevent_preview(self):
        for extra in ({'synthetic_confirmed':''},{'amount':'1.001'},{'effective_on':'invalid'}):
            response=self.client.post(reverse('ledger_demo_new'),{**self.data,**extra})
            self.assertTrue(response.context['form'].errors)
        self.assertEqual(DemoBook.objects.count(),0)

    def test_roles_and_foreign_book_access(self):
        book,token=self.open()
        self.client.force_login(self.users['viewer'])
        self.assertEqual(self.client.get(reverse('ledger_demo_detail',args=[book.pk])).status_code,200)
        self.assertEqual(self.client.get(reverse('ledger_demo_new')).status_code,403)
        self.assertEqual(self.confirm(token).status_code,403)
        self.client.force_login(self.users['foreign'])
        self.assertEqual(self.client.get(reverse('ledger_demo_detail',args=[book.pk])).status_code,404)
        self.assertEqual(self.confirm(token).status_code,403)

    def test_tampered_token_csrf_methods_and_private_headers(self):
        self.assertEqual(self.confirm('invalid').status_code,400)
        strict=Client(enforce_csrf_checks=True);strict.force_login(self.users['staff'])
        self.assertEqual(strict.post(reverse('ledger_demo_new'),self.data).status_code,403)
        self.assertEqual(self.client.get(reverse('ledger_demo_confirm')).status_code,405)
        self.assertIn('no-store',self.client.get(reverse('ledger_demo_list'))['Cache-Control'])

    @override_settings(DEMO_LEDGER_ENABLED=False)
    def test_disabled_routes_do_not_expose_forms(self):
        for name in ('ledger_demo_list','ledger_demo_new'):
            self.assertEqual(self.client.get(reverse(name)).status_code,403)
        self.assertEqual(self.confirm('invalid').status_code,403)
