
from typing import Optional, Dict, Any, List
from ..models import AssessmentInstance, AssessmentQuestion, AssessmentInstanceResponseVector


class AssessmentFlowEngine:
    """
    Handles assessment flow logic and question sequencing
    """
    
    def __init__(self, assessment_instance: AssessmentInstance):
        self.assessment_instance = assessment_instance
        self.campaign = assessment_instance.campaign

    def get_next_question(self) -> Optional[Dict[str, Any]]:
        """Get the next question based on flow logic"""
        
        # Check for conditional logic
        next_question = self._apply_conditional_logic()
        if next_question:
            return next_question
        
        # Default: get next planned question
        next_planned_question = self.assessment_instance.responses.filter(
            done=False, 
            planned=True
        ).order_by('question__order').first()
        
        if not next_planned_question:
            return None
        
        return self._format_question_response(next_planned_question)

    def _apply_conditional_logic(self) -> Optional[Dict[str, Any]]:
        """Apply conditional logic to determine next question"""
        
        # Get all completed responses
        completed_responses = self.assessment_instance.responses.filter(done=True)
        
        for response in completed_responses:
            question = response.question
            conditional_logic = question.conditional_logic
            
            if not conditional_logic:
                continue
            
            # Process conditional rules
            for rule in conditional_logic.get('rules', []):
                if self._evaluate_condition(rule, response):
                    action = rule.get('action')
                    
                    if action == 'skip_to':
                        target_question_id = rule.get('target_question_id')
                        return self._get_question_by_id(target_question_id)
                    
                    elif action == 'skip_questions':
                        question_ids_to_skip = rule.get('question_ids', [])
                        self._mark_questions_as_skipped(question_ids_to_skip)
        
        return None

    def _evaluate_condition(self, rule: Dict[str, Any], response) -> bool:
        """Evaluate if a conditional rule matches the response"""
        condition_type = rule.get('condition_type')
        condition_value = rule.get('condition_value')
        
        response_data = response.response
        
        if condition_type == 'option_selected':
            selected_options = response_data.get('selected_options', [])
            return any(opt['option_id'] == condition_value for opt in selected_options)
        
        elif condition_type == 'text_contains':
            text = response_data.get('text', '').lower()
            return condition_value.lower() in text
        
        elif condition_type == 'value_greater_than':
            selected_options = response_data.get('selected_options', [])
            total_value = sum(opt.get('value', 0) for opt in selected_options)
            return total_value > condition_value
        
        # Add more condition types as needed
        return False

    def _get_question_by_id(self, question_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific question by ID"""
        try:
            response_vector = self.assessment_instance.responses.get(
                question_id=question_id,
                done=False
            )
            return self._format_question_response(response_vector)
        except AssessmentInstanceResponseVector.DoesNotExist:
            return None

    def _mark_questions_as_skipped(self, question_ids: List[str]):
        """Mark questions as completed/skipped"""
        self.assessment_instance.responses.filter(
            question_id__in=question_ids,
            done=False
        ).update(
            done=True,
            planned=False,
            response={'skipped': True}
        )

    def _format_question_response(self, response_vector) -> Dict[str, Any]:
        """Format question data for frontend"""
        question = response_vector.question
        options = question.options.all().order_by('order')
        
        return {
            "response_vector_id": str(response_vector.id),
            "question_id": str(question.id),
            "question": question.question,
            "description": question.description,
            "type": question.type,
            "configuration": question.configuration,
            "optional": question.optional,
            "image": question.image.url if question.image else None,
            "options": [
                {
                    "id": str(option.id),
                    "option": option.option,
                    "meaning": option.meaning,
                    "value": option.value,
                    "image": option.image.url if option.image else None
                }
                for option in options
            ],
            "validation_rules": question.validation_rules,
            "topic": question.topic
        }

    def calculate_progress(self) -> Dict[str, Any]:
        """Calculate assessment progress"""
        total_questions = self.assessment_instance.total_questions
        completed = self.assessment_instance.responses.filter(done=True).count()
        
        return {
            'total_questions': total_questions,
            'completed_questions': completed,
            'remaining_questions': total_questions - completed,
            'progress_percentage': (completed / total_questions * 100) if total_questions > 0 else 0,
            'current_step': self.assessment_instance.step
        }

    def get_assessment_summary(self) -> Dict[str, Any]:
        """Get a summary of the assessment state"""
        progress = self.calculate_progress()
        
        return {
            'instance_id': str(self.assessment_instance.id),
            'campaign_name': self.campaign.name,
            'status': self.assessment_instance.status,
            'progress': progress,
            'created_at': self.assessment_instance.created_at,
            'updated_at': self.assessment_instance.updated_at,
            'llm_enabled': self.campaign.llm_enabled
        }
