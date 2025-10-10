# lupon_mem/models.py
from django.db import models

class KpForm(models.Model):
    form_id = models.AutoField(primary_key=True)   # SERIAL in DB
    form_code = models.TextField()
    form_name = models.TextField()
    class Meta:
        managed = False
        db_table = 'kp_form'

class KpFieldType(models.Model):
    field_type_id = models.AutoField(primary_key=True)
    field_type_name = models.TextField()
    class Meta:
        managed = False
        db_table = 'kp_field_type'

class KpField(models.Model):
    field_id = models.AutoField(primary_key=True)
    field_code = models.TextField()
    base_label = models.TextField()
    field_type = models.ForeignKey(KpFieldType, on_delete=models.DO_NOTHING, db_column='field_type_id')
    class Meta:
        managed = False
        db_table = 'kp_field'

class KpFormField(models.Model):
    kp_form_field_id = models.AutoField(primary_key=True)
    form = models.ForeignKey(KpForm, on_delete=models.CASCADE, db_column='form_id', related_name='form_fields')
    field = models.ForeignKey(KpField, on_delete=models.DO_NOTHING, db_column='field_id')
    sort_order = models.IntegerField()
    label_override = models.TextField(null=True)
    class Meta:
        managed = False
        db_table = 'kp_form_field'

class BlotterKpSubmission(models.Model):
    submission_id = models.AutoField(primary_key=True)
    blotter_case_id = models.IntegerField()
    form = models.ForeignKey(KpForm, on_delete=models.DO_NOTHING, db_column='form_id')
    status = models.TextField()
    submitted_at = models.DateTimeField()
    class Meta:
        managed = False
        db_table = 'blotter_kp_submission'

class BlotterKpAnswer(models.Model):
    answer_id = models.AutoField(primary_key=True)
    submission = models.ForeignKey(BlotterKpSubmission, on_delete=models.CASCADE, db_column='submission_id', related_name='answers')
    field = models.ForeignKey(KpField, on_delete=models.DO_NOTHING, db_column='field_id')
    value_json = models.JSONField(null=True)
    class Meta:
        managed = False
        db_table = 'blotter_kp_answer'
