# SPDX-License-Identifier: MPL-2.0

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('deals', '0011_completion_guards'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DemoCompletionVoid',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reason', models.CharField(max_length=1000)),
                ('review_sha256', models.CharField(max_length=64)),
                ('creation_key', models.UUIDField(editable=False, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('policy_version', models.CharField(default='demo-completion-void-v1', editable=False, max_length=40)),
                ('actor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ('completion', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='void_rehearsal', to='deals.demodealcompletion')),
            ],
        ),
    ]
