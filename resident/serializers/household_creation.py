from rest_framework import serializers

from resident.serializers.base import BaseSerializer  

class HouseholdCreationSerializer(serializers.Serializer):
    
    resident_id = serializers.CharField(
        max_length=20,
        required=True,
        error_messages={
            'required': 'Resident ID is required.',
            'blank': 'Resident ID cannot be blank.',
            'max_length': 'Resident ID cannot exceed 20 characters.'
        }
    )
    
    house_number = serializers.CharField(
        max_length=100,
        required=True,
        error_messages={
            'required': 'House number is required.',
            'blank': 'House number cannot be blank.',
            'max_length': 'House number cannot exceed 100 characters.'
        },
    )
    
    street = serializers.CharField(
        max_length=100,
        required=True,
        error_messages={
            'required': 'Street is required.',
            'blank': 'Street cannot be blank.',
            'max_length': 'Street cannot exceed 100 characters.'
        },

    )
    
    sitio = serializers.CharField(
        max_length=100,
        required=True,
        error_messages={
            'required': 'Sitio is required.',
            'blank': 'Sitio cannot be blank.',
            'max_length': 'Sitio cannot exceed 100 characters.'
        },
    )
    
    barangay = serializers.CharField(
        max_length=100,
        required=True,
        error_messages={
            'required': 'Barangay is required.',
            'blank': 'Barangay cannot be blank.',
            'max_length': 'Barangay cannot exceed 100 characters.'
        },
    )
    
    city = serializers.CharField(
        max_length=100,
        required=True,
        error_messages={
            'required': 'City is required.',
            'blank': 'City cannot be blank.',
            'max_length': 'City cannot exceed 100 characters.'
        },
    )
    
    house_type = serializers.IntegerField(
        required=True,
        error_messages={
            'required': 'House type is required.',
        },
    )
    
    ownership = serializers.IntegerField(
        required=True,
        error_messages={
            'required': 'Ownership is required.',
        },
    )
    
    message = serializers.CharField(
        required=False,
        max_length=500,
        error_messages={
            'max_length': 'Message cannot exceed 500 characters.'
        }
    )