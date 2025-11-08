# lupon_pres/models.py
from django.db import models

# Create your models here.

# Note: lupon_pres uses the same database models as lupon_mem
# The models are defined in the shared database schema and accessed
# through raw SQL queries in the services layer.

# Key models that would be used (defined elsewhere in the system):
# - BlotterCase
# - BlotterKpSubmission  
# - KpForm
# - KpField
# - BlotterKpAnswer
# - CaseProgressTracking
# - CaseProgressType
# - SettlementStatus
# - CaseState
# - Person
# - Staff

class BlotterKpSubmission(models.Model):
    """Proxy model for blotter_kp_submission table"""
    class Meta:
        managed = False
        db_table = 'blotter_kp_submission'

class KpFormField(models.Model):
    """Proxy model for kp_form_field table"""
    class Meta:
        managed = False
        db_table = 'kp_form_field'

class KpField(models.Model):
    """Proxy model for kp_field table"""
    class Meta:
        managed = False
        db_table = 'kp_field'

class BlotterKpAnswer(models.Model):
    """Proxy model for blotter_kp_answer table"""
    class Meta:
        managed = False
        db_table = 'blotter_kp_answer'