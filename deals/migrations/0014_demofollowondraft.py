# SPDX-License-Identifier: MPL-2.0

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('deals', '0013_void_immutability'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DemoFollowOnDraft',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reason', models.CharField(max_length=1000)),
                ('review_sha256', models.CharField(max_length=64)),
                ('creation_key', models.UUIDField(editable=False, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('policy_version', models.CharField(default='demo-follow-on-draft-v1', editable=False, max_length=40)),
                ('actor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ('draft', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='source_follow_on', to='deals.draftdeal')),
                ('void_rehearsal', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='follow_on_draft', to='deals.democompletionvoid')),
            ],
        ),
    ]
