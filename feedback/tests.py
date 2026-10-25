# SPDX-License-Identifier: MPL-2.0
import uuid
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from core.models import Dealership, Membership
from .models import FeedbackReport
from .views import SALT


class FeedbackTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dealer = Dealership.objects.create(name='Synthetic dealer')
        cls.other = Dealership.objects.create(name='Other synthetic dealer')
        cls.users = {}
        for name, role, dealer in [('staff', 'staff', cls.dealer), ('viewer', 'viewer', cls.dealer), ('owner', 'owner', cls.dealer), ('outsider', 'owner', cls.other)]:
            user = get_user_model().objects.create_user(name)
            Membership.objects.create(user=user, role=role, dealership=dealer)
            cls.users[name] = user

    def setUp(self):
        self.client.force_login(self.users['staff'])
        self.data = {'submission_key': str(uuid.uuid4()), 'kind': 'bug', 'area': 'inventory', 'subject': 'Synthetic filter issue', 'expected': 'Find a synthetic vehicle.', 'actual': 'The list is empty.', 'privacy_checked': 'on'}

    def preview(self, data=None):
        response = self.client.post(reverse('feedback_create'), data or self.data)
        self.assertEqual(response.status_code, 200)
        return response.context['token']

    def save(self, token):
        return self.client.post(reverse('feedback_confirm'), {'preview_token': token, 'action': 'save'})

    def test_preview_does_not_save_and_confirm_uses_only_signed_fields(self):
        token = self.preview()
        self.assertEqual(FeedbackReport.objects.count(), 0)
        response = self.client.post(reverse('feedback_confirm'), {'preview_token': token, 'action': 'save', 'subject': 'Forged override', 'author': self.users['outsider'].pk})
        self.assertEqual(response.status_code, 302)
        report = FeedbackReport.objects.get()
        self.assertEqual(report.subject, self.data['subject'])
        self.assertEqual(report.author, self.users['staff'])
        self.assertEqual(report.dealership, self.dealer)

    def test_retries_return_same_report(self):
        token = self.preview()
        first = self.save(token)
        second = self.save(token)
        self.assertEqual(first.url, second.url)
        self.assertEqual(FeedbackReport.objects.count(), 1)

    def test_conflicting_reuse_does_not_overwrite(self):
        self.save(self.preview())
        changed = {**self.data, 'actual': 'A different report version.'}
        response = self.save(self.preview(changed))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(FeedbackReport.objects.get().actual, self.data['actual'])

    def test_invalid_fields_preserve_work_and_require_privacy_ack(self):
        response = self.client.post(reverse('feedback_create'), {**self.data, 'privacy_checked': ''})
        self.assertFormError(response.context['form'], 'privacy_checked', 'This field is required.')
        self.assertContains(response, self.data['actual'])
        self.assertEqual(FeedbackReport.objects.count(), 0)

    def test_bad_or_expired_signature_does_not_save(self):
        token = self.preview()
        self.assertEqual(self.save(token+'tampered').status_code, 400)
        with patch('django.core.signing.time.time', return_value=10):
            old = self.preview()
        self.assertEqual(self.save(old).status_code, 400)
        self.assertEqual(FeedbackReport.objects.count(), 0)

    def test_preview_is_bound_to_author_and_dealer(self):
        token = self.preview()
        for name in ('viewer', 'owner', 'outsider'):
            self.client.force_login(self.users[name])
            self.assertEqual(self.save(token).status_code, 403)
        self.assertEqual(FeedbackReport.objects.count(), 0)

    def test_own_reports_and_owner_access_are_scoped(self):
        self.save(self.preview())
        report = FeedbackReport.objects.get()
        for name, status in [('staff', 200), ('viewer', 404), ('owner', 200), ('outsider', 404)]:
            self.client.force_login(self.users[name])
            response = self.client.get(reverse('feedback_detail', args=[report.pk]))
            self.assertEqual(response.status_code, status)
            listing = self.client.get(reverse('feedback_list'))
            self.assertEqual(len(listing.context['page']), 1 if status==200 else 0)

    def test_viewer_can_report_without_editing_dealership_records(self):
        self.client.force_login(self.users['viewer'])
        self.assertEqual(self.save(self.preview()).status_code, 302)
        self.assertEqual(FeedbackReport.objects.get().author, self.users['viewer'])

    def test_edit_round_trip_preserves_values_without_saving(self):
        token = self.preview()
        response = self.client.post(reverse('feedback_confirm'), {'preview_token': token, 'action': 'edit'})
        self.assertEqual(response.context['form']['actual'].value(), self.data['actual'])
        self.assertEqual(str(response.context['form']['submission_key'].value()), self.data['submission_key'])
        self.assertEqual(FeedbackReport.objects.count(), 0)

    def test_attachments_are_rejected_and_no_record_is_saved(self):
        response = self.client.post(reverse('feedback_create'), {**self.data, 'file': SimpleUploadedFile('private.txt', b'synthetic')})
        self.assertContains(response, 'Attachments are not accepted.')
        token = self.preview()
        response = self.client.post(reverse('feedback_confirm'), {'preview_token': token, 'action': 'save', 'file': SimpleUploadedFile('private.txt', b'synthetic')})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(FeedbackReport.objects.count(), 0)

    def test_html_is_escaped_and_private_pages_are_not_cached(self):
        token = self.preview({**self.data, 'actual': '<script>alert("synthetic")</script>'})
        response = self.save(token)
        detail = self.client.get(response.url)
        self.assertContains(detail, '&lt;script&gt;')
        self.assertNotContains(detail, '<script>alert(')
        self.assertIn('no-store', detail['Cache-Control'])
        self.assertIn('private', detail['Cache-Control'])

    def test_login_csrf_and_http_method_controls(self):
        anonymous = Client()
        for name in ('feedback_create', 'feedback_list'):
            self.assertEqual(anonymous.get(reverse(name)).status_code, 302)
        self.assertEqual(self.client.get(reverse('feedback_confirm')).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.users['staff'])
        self.assertEqual(strict.post(reverse('feedback_create'), self.data).status_code, 403)
        self.assertEqual(strict.post(reverse('feedback_confirm'), {'preview_token': self.preview(), 'action': 'save'}).status_code, 403)
