from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0005_asset_change_request'),
    ]

    operations = [
        migrations.AlterField(
            model_name='server',
            name='status',
            field=models.CharField(
                choices=[('Running', '运行中'), ('Stopped', '已停止'), ('Retired', '已退役')],
                default='Running', max_length=32, verbose_name='实例状态'),
        ),
    ]
