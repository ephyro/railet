# SPDX-License-Identifier: MPL-2.0
import uuid
from django.conf import settings
from django.db import models


class DemoBook(models.Model):
    dealership = models.ForeignKey('core.Dealership', on_delete=models.PROTECT)
    customer = models.ForeignKey('customers.Customer', on_delete=models.PROTECT)
    label = models.CharField(max_length=100)
    source_reference = models.CharField(max_length=300)
    opening_on = models.DateField()
    currency = models.CharField(max_length=3, default='USD', editable=False)
    creation_key = models.UUIDField(default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at','-pk']
        constraints = [models.UniqueConstraint(fields=['dealership','creation_key'],name='unique_demo_book_key'), models.CheckConstraint(condition=models.Q(currency='USD'),name='demo_book_usd_only')]


class DemoPosting(models.Model):
    class Kind(models.TextChoices):
        OPENING = 'opening','Synthetic opening balance'
        RECEIPT = 'receipt','Synthetic unapplied receipt'
        REVERSAL = 'reversal','Receipt correction'
    class Bucket(models.TextChoices):
        PRINCIPAL = 'principal','Opening principal'
        OPENING_OFFSET = 'opening_offset','Opening offset'
        CASH = 'cash_control','Cash control (not settlement)'
        UNAPPLIED = 'unapplied','Unapplied receipts'
    class PaymentMethod(models.TextChoices):
        UNSPECIFIED = 'unspecified','Not recorded'
        CASH = 'cash','Cash'
        CHECK = 'check','Check'
        OTHER = 'other','Other'
    payment_method = models.CharField(max_length=16,choices=PaymentMethod.choices,default=PaymentMethod.UNSPECIFIED)
    book = models.ForeignKey(DemoBook, on_delete=models.PROTECT, related_name='postings')
    kind = models.CharField(max_length=12, choices=Kind.choices)
    amount_cents = models.BigIntegerField()
    debit = models.CharField(max_length=20, choices=Bucket.choices)
    credit = models.CharField(max_length=20, choices=Bucket.choices)
    reverses = models.OneToOneField('self',on_delete=models.PROTECT,null=True,blank=True,related_name='reversal')
    request_key = models.UUIDField(default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.CharField(max_length=300)
    effective_on = models.DateField()
    entered_at = models.DateTimeField(auto_now_add=True)
    posting_version = models.CharField(max_length=40, default='demo-unapplied-v1',editable=False)

    class Meta:
        ordering = ['entered_at','pk']
        constraints = [
            models.UniqueConstraint(fields=['book','request_key'],name='unique_demo_posting_key'),
            models.UniqueConstraint(fields=['book'],condition=models.Q(kind='opening'),name='one_demo_opening_per_book'),
            models.CheckConstraint(condition=models.Q(amount_cents__gt=0,amount_cents__lte=999999999999),name='demo_posting_positive_bounded'),
            models.CheckConstraint(condition=(
                models.Q(kind='opening',debit='principal',credit='opening_offset',reverses__isnull=True)
                | models.Q(kind='receipt',debit='cash_control',credit='unapplied',reverses__isnull=True)
                | models.Q(kind='reversal',debit='unapplied',credit='cash_control',reverses__isnull=False)
            ),name='demo_posting_balanced_pair'),
        ]


class DemoSchedule(models.Model):
    book = models.ForeignKey(DemoBook,on_delete=models.PROTECT,related_name='schedule_illustrations')
    method = models.CharField(max_length=20,choices=[('precomputed','Precomputed'),('simple_daily','Daily simple illustration')])
    calculation_version = models.CharField(max_length=40)
    inputs = models.JSONField()
    result = models.JSONField()
    result_sha256 = models.CharField(max_length=64)
    creation_key = models.UUIDField(default=uuid.uuid4,editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering=['-created_at','-pk']
        constraints=[models.UniqueConstraint(fields=['book','creation_key'],name='unique_demo_schedule_key'),models.CheckConstraint(condition=models.Q(method__in=['precomputed','simple_daily']),name='demo_schedule_method_known')]


class DemoAccountContext(models.Model):
    """Frozen draft context; linking does not create or amend a contract."""
    book = models.OneToOneField(DemoBook, on_delete=models.PROTECT, related_name='account_context')
    deal = models.ForeignKey('deals.DraftDeal', on_delete=models.PROTECT)
    snapshot = models.JSONField()
    snapshot_sha256 = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['deal'], name='one_demo_account_per_draft')]


class DemoAccountExport(models.Model):
    book = models.ForeignKey(DemoBook, on_delete=models.PROTECT, related_name='export_events')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    format_version = models.CharField(max_length=40, default='demo-account-export-v4')
    bundle_sha256 = models.CharField(max_length=64)
    bundle_bytes = models.PositiveIntegerField()
    posting_count = models.PositiveIntegerField()
    schedule_count = models.PositiveIntegerField()

    class Meta:
        ordering = ['-created_at', '-pk']


class DemoServicingPlan(models.Model):
    """Explicit immutable simulation baseline, not an originated contract."""
    book = models.OneToOneField(DemoBook,on_delete=models.PROTECT,related_name='servicing_plan')
    schedule = models.ForeignKey(DemoSchedule,on_delete=models.PROTECT)
    schedule_sha256 = models.CharField(max_length=64)
    policy_version = models.CharField(max_length=40,default='monthly-oldest-first-v1',editable=False)
    reason = models.CharField(max_length=300)
    creation_key = models.UUIDField(default=uuid.uuid4,unique=True,editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints=[models.CheckConstraint(condition=models.Q(policy_version='monthly-oldest-first-v1'),name='demo_servicing_policy_known')]
