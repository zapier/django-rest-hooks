# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rest_hooks', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='Hook',
            options={
                'swappable': 'HOOK_CUSTOM_MODEL',
            },
        ),
    ]
