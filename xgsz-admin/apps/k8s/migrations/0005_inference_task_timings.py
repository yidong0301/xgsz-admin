from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('k8s', '0004_inference_task_service'),
    ]

    operations = [
        migrations.AddField(
            model_name='inferencetask',
            name='started_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='开始运行时间'),
        ),
        migrations.AddField(
            model_name='inferencetask',
            name='finished_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='结束时间'),
        ),
    ]
