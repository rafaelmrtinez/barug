from rest_framework import serializers

class ChatSerializer(serializers.Serializer):
    """
    Serializer for handling chat messages and responses.
    
    This serializer is used to validate and serialize chat messages sent to the AI chat view.
    """
    
    prompt = serializers.CharField(
        required=True, 
        max_length=500, 
        help_text="The chat message to be processed by the AI.", 
        error_messages={
        'required': 'Chat message is required.',
        'max_length': 'Chat message cannot exceed 500 characters.'
    })