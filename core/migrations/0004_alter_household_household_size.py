# Generated by Django 5.2.1 on 2025-06-05 02:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_alter_residencyrequest_request_type_alter_user_role'),
    ]

    operations = [
        migrations.AlterField(
            model_name='household',
            name='household_size',
            field=models.IntegerField(default=1),
        ),
    ]
