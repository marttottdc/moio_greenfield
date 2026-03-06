
import uuid

from django.contrib.auth import get_user_model
from django.db import models

from portal.models import Tenant

User = get_user_model()


class AssessmentInstanceStatus(models.TextChoices):
    NEW = 'N', 'Nueva'
    QUESTIONS_LOOP = 'Q', 'Questions Loop'
    S1_PLANNED = 'S1', 'S1 Planned'
    READY = 'R', 'Ready'
    COMPLETED = 'C', 'Completed'
    CANCELLED = 'X', 'Cancelled'

    def __str__(self):
        return self.label


class CampaignTypes(models.TextChoices):
    Form = 'FORM', 'Form'
    Diagnostic = 'DIAG', 'Diagnostic'
    Survey = 'SURV', 'Survey'
    Quiz = 'QUIZ', 'Quiz'


class AssessmentCampaign(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField()
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    active = models.BooleanField(default=True)
    public = models.BooleanField(default=False)
    type = models.CharField(max_length=4, choices=CampaignTypes.choices, default=CampaignTypes.Form)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # LLM Integration settings
    llm_enabled = models.BooleanField(default=False)
    llm_assistant_prompt = models.TextField(blank=True)
    llm_content_generation = models.BooleanField(default=False)
    llm_flow_management = models.BooleanField(default=False)

    class Meta:
        unique_together = ['name', 'tenant']

    def __str__(self):
        return self.name


class PainPoint(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField()
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)

    def __str__(self):
        return self.name


class QuestionTypes(models.TextChoices):
    Welcome = 'WEL', 'Welcome'
    InputWithOptions = 'IWO', 'Input With Options'
    ShortInput = 'SHI', 'Short Input'
    LongInput = 'LOI', 'Long Input'
    Options = 'OPT', 'Options'
    Contact = 'CON', 'Contact Data'
    Date = 'DAT', 'Date Data'
    Scale = 'SCA', 'Scale Rating'
    MultipleChoice = 'MUL', 'Multiple Choice'


class AssessmentQuestion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.CharField(max_length=300, null=False)
    type = models.CharField(max_length=3, choices=QuestionTypes.choices, default="SHI", null=False)
    configuration = models.JSONField(default=dict)
    question_group = models.IntegerField(default=0)
    optional = models.BooleanField(default=False)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    description = models.TextField()
    campaign = models.ForeignKey(AssessmentCampaign, related_name="questions", on_delete=models.CASCADE)
    topic = models.CharField(max_length=100, null=False, default="any")
    image = models.ImageField(upload_to="assessment_question_images", null=True, blank=True)
    
    # Validation rules
    validation_rules = models.JSONField(default=dict)
    conditional_logic = models.JSONField(default=dict)

    class Meta:
        ordering = ['order', 'created_at']
        unique_together = ['campaign', 'order']

    def __str__(self):
        return self.question


class AssessmentQuestionOption(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(AssessmentQuestion, related_name="options", on_delete=models.CASCADE)
    option = models.CharField(max_length=100, null=False)
    meaning = models.CharField(max_length=300, default="")
    image = models.ImageField(upload_to="assessment_question_images", null=True, blank=True)
    order = models.IntegerField(default=0)
    value = models.IntegerField(null=True, blank=True)  # For scoring

    class Meta:
        ordering = ['order']
        unique_together = ['question', 'order']

    def __str__(self):
        return self.option


class AssessmentInstance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=2, choices=AssessmentInstanceStatus.choices, default=AssessmentInstanceStatus.NEW)
    step = models.IntegerField(default=0)
    campaign = models.ForeignKey(AssessmentCampaign, related_name="assessment_instances", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    # Progress tracking
    total_questions = models.IntegerField(default=0)
    answered_questions = models.IntegerField(default=0)
    
    # Results
    score = models.JSONField(default=dict)
    insights = models.TextField(blank=True)

    def __str__(self):
        return str(self.id)

    @property
    def progress_percentage(self):
        if self.total_questions == 0:
            return 0
        return (self.answered_questions / self.total_questions) * 100

    def display(self):
        for field in self._meta.fields:
            print(f'Field {field.name}: {getattr(self, field.name)}')


class AssessmentInstanceResponseVector(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    instance = models.ForeignKey(AssessmentInstance, related_name="responses", on_delete=models.CASCADE)
    question = models.ForeignKey(AssessmentQuestion, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    planned = models.BooleanField(default=False)
    mandatory = models.BooleanField(default=False)
    done = models.BooleanField(default=False)
    response = models.JSONField(default=dict)
    
    # Validation
    is_valid = models.BooleanField(default=True)
    validation_errors = models.JSONField(default=list)

    class Meta:
        unique_together = ['instance', 'question']

    def __str__(self):
        return str(self.id)
