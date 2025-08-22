# clerk/serializers.py
from rest_framework import serializers

class ApprovePersonByClerkSerializer(serializers.Serializer):
    clerk_staff_id = serializers.IntegerField()
    person_id      = serializers.IntegerField()
    request_id     = serializers.IntegerField()
    status_id      = serializers.IntegerField()
    remarks        = serializers.CharField(required=False, allow_blank=True, allow_null=True)
