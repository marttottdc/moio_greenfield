
import uuid
from django.db import models
from .assessment_data import AssessmentCampaign, AssessmentInstance


class LLMAssistantConfig(models.Model):
    """Configuration for LLM assistant integration with assessments"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.OneToOneField(AssessmentCampaign, on_delete=models.CASCADE, related_name='llm_config')
    
    # Assistant configuration
    assistant_id = models.CharField(max_length=100)
    system_prompt = models.TextField()
    content_generation_prompt = models.TextField(blank=True)
    flow_management_prompt = models.TextField(blank=True)
    
    # Behavior settings
    auto_generate_questions = models.BooleanField(default=False)
    adaptive_questioning = models.BooleanField(default=False)
    real_time_insights = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"LLM Config for {self.campaign.name}"


class LLMInteraction(models.Model):
    """Track LLM interactions during assessment"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assessment_instance = models.ForeignKey(AssessmentInstance, on_delete=models.CASCADE, related_name='llm_interactions')
    
    interaction_type = models.CharField(max_length=50, choices=[
        ('question_generation', 'Question Generation'),
        ('content_suggestion', 'Content Suggestion'),
        ('flow_decision', 'Flow Decision'),
        ('insight_generation', 'Insight Generation'),
        ('validation', 'Response Validation'),
    ])
    
    prompt = models.TextField()
    response = models.TextField()
    metadata = models.JSONField(default=dict)
    
    created_at = models.DateTimeField(auto_now_add=True)
    processing_time = models.FloatField(null=True)  # in seconds

    def __str__(self):
        return f"{self.interaction_type} - {self.assessment_instance.id}"
