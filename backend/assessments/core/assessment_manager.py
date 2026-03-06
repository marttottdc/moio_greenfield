
from typing import Dict, Any, Optional, List
from django.db import transaction
from django.utils import timezone

from ..models import (
    AssessmentInstance, Campaign, AssessmentQuestion, 
    AssessmentQuestionOption, AssessmentInstanceResponseVector,
    AssessmentInstanceStatus
)
from .llm_assistant import LLMAssessmentAssistant
from .flow_engine import AssessmentFlowEngine


class AssessmentManager:
    """
    Enhanced assessment manager with LLM integration and better flow control
    """
    
    def __init__(self, assessment_instance: AssessmentInstance):
        self.assessment_instance = assessment_instance
        self.id = assessment_instance.id
        self.status = assessment_instance.status
        self.step = assessment_instance.step
        self.campaign = assessment_instance.campaign
        
        # Initialize components
        self.flow_engine = AssessmentFlowEngine(assessment_instance)
        self.llm_assistant = None
        
        if self.campaign.llm_enabled:
            self.llm_assistant = LLMAssessmentAssistant(assessment_instance)
        
        self.message = "Manager Created"

    def initialize_assessment(self) -> Dict[str, Any]:
        """Initialize a new assessment instance"""
        try:
            with transaction.atomic():
                # Create response vectors for all questions
                questions = AssessmentQuestion.objects.filter(
                    campaign=self.campaign
                ).order_by('order')
                
                for question in questions:
                    AssessmentInstanceResponseVector.objects.get_or_create(
                        instance=self.assessment_instance,
                        question=question,
                        defaults={
                            'planned': True,
                            'mandatory': not question.optional
                        }
                    )
                
                # Update instance
                self.assessment_instance.total_questions = questions.count()
                self.assessment_instance.status = AssessmentInstanceStatus.QUESTIONS_LOOP
                self.assessment_instance.save()
                
                # Get first question
                first_question = self.get_next_step()
                
                return {
                    'success': True,
                    'next_question': first_question,
                    'message': 'Assessment initialized successfully'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Failed to initialize assessment'
            }

    def handle_response(self, request) -> Dict[str, Any]:
        """Handle user response with improved validation and LLM integration"""
        if request.method != "POST":
            return {'success': False, 'error': 'Invalid request method'}
        
        action = request.POST.get("action")
        response_id = request.POST.get("response_id")
        
        try:
            with transaction.atomic():
                response_vector = AssessmentInstanceResponseVector.objects.get(id=response_id)
                
                # Validate and process response
                validation_result = self._validate_response(response_vector, request.POST)
                
                if not validation_result['is_valid']:
                    return {
                        'success': False,
                        'errors': validation_result['errors'],
                        'message': 'Response validation failed'
                    }
                
                # Save response
                response_vector.response = validation_result['processed_response']
                response_vector.planned = False
                response_vector.done = True
                response_vector.is_valid = True
                response_vector.save()
                
                # Update progress
                self._update_progress()
                
                # LLM processing if enabled
                if self.llm_assistant:
                    llm_result = self.llm_assistant.process_response(response_vector)
                    if llm_result.get('insights'):
                        self.assessment_instance.insights += f"\n{llm_result['insights']}"
                        self.assessment_instance.save()
                
                # Determine next step
                next_step = self.flow_engine.get_next_question()
                
                return {
                    'success': True,
                    'next_question': next_step,
                    'progress': self.assessment_instance.progress_percentage,
                    'message': f"Response recorded for {response_vector.question.question}"
                }
                
        except AssessmentInstanceResponseVector.DoesNotExist:
            return {'success': False, 'error': 'Response vector not found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _validate_response(self, response_vector: AssessmentInstanceResponseVector, 
                          post_data: Dict) -> Dict[str, Any]:
        """Validate user response based on question type and rules"""
        question = response_vector.question
        errors = []
        
        # Basic validation based on question type
        if question.type == 'OPT':  # Options
            selected_options = []
            for option in question.options.all():
                if post_data.get(str(option.id)):
                    selected_options.append({
                        'option_id': str(option.id),
                        'option_text': option.option,
                        'value': option.value
                    })
            
            if not selected_options and response_vector.mandatory:
                errors.append("This question requires a response")
            
            processed_response = {'selected_options': selected_options}
            
        elif question.type in ['SHI', 'LOI']:  # Text inputs
            text_response = post_data.get('text_response', '').strip()
            
            if not text_response and response_vector.mandatory:
                errors.append("This question requires a response")
            
            # Apply validation rules
            validation_rules = question.validation_rules
            if validation_rules.get('min_length') and len(text_response) < validation_rules['min_length']:
                errors.append(f"Response must be at least {validation_rules['min_length']} characters")
            
            processed_response = {'text': text_response}
            
        else:
            processed_response = {'raw_data': dict(post_data)}
        
        return {
            'is_valid': len(errors) == 0,
            'errors': errors,
            'processed_response': processed_response
        }

    def _update_progress(self):
        """Update assessment progress"""
        answered = self.assessment_instance.responses.filter(done=True).count()
        self.assessment_instance.answered_questions = answered
        
        if answered >= self.assessment_instance.total_questions:
            self.assessment_instance.status = AssessmentInstanceStatus.COMPLETED
            self.assessment_instance.completed_at = timezone.now()
        
        self.assessment_instance.save()

    def get_next_step(self) -> Optional[Dict[str, Any]]:
        """Get the next question in the assessment"""
        return self.flow_engine.get_next_question()

    def generate_insights(self) -> Dict[str, Any]:
        """Generate insights using LLM if available"""
        if not self.llm_assistant:
            return {'success': False, 'message': 'LLM not enabled for this campaign'}
        
        return self.llm_assistant.generate_final_insights()

    def get_results(self) -> Dict[str, Any]:
        """Get assessment results and analytics"""
        responses = self.assessment_instance.responses.filter(done=True)
        
        results = {
            'instance_id': str(self.assessment_instance.id),
            'campaign': self.campaign.name,
            'status': self.assessment_instance.status,
            'progress': self.assessment_instance.progress_percentage,
            'total_questions': self.assessment_instance.total_questions,
            'answered_questions': self.assessment_instance.answered_questions,
            'created_at': self.assessment_instance.created_at,
            'completed_at': self.assessment_instance.completed_at,
            'responses': [],
            'insights': self.assessment_instance.insights,
            'score': self.assessment_instance.score
        }
        
        for response in responses:
            results['responses'].append({
                'question': response.question.question,
                'type': response.question.type,
                'response': response.response,
                'created_at': response.created_at
            })
        
        return results

    def get_message(self) -> str:
        return self.message
