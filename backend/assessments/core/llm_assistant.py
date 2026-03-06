
from typing import Dict, Any, Optional
from django.utils import timezone
import json

from ..models import AssessmentInstance, LLMInteraction, LLMAssistantConfig
from portal.models import TenantConfiguration


class LLMAssessmentAssistant:
    """
    LLM assistant for assessment generation, flow management, and insights
    """
    
    def __init__(self, assessment_instance: AssessmentInstance):
        self.assessment_instance = assessment_instance
        self.campaign = assessment_instance.campaign
        self.tenant_config = TenantConfiguration.objects.get(tenant=self.campaign.tenant)
        
        try:
            self.llm_config = LLMAssistantConfig.objects.get(campaign=self.campaign)
        except LLMAssistantConfig.DoesNotExist:
            self.llm_config = None

    def process_response(self, response_vector) -> Dict[str, Any]:
        """Process a response and generate insights"""
        if not self.llm_config or not self.llm_config.real_time_insights:
            return {'insights': None}
        
        prompt = self._build_response_analysis_prompt(response_vector)
        
        try:
            # Call LLM for response analysis
            llm_response = self._call_llm(prompt, 'insight_generation')
            
            return {
                'insights': llm_response.get('insights'),
                'suggestions': llm_response.get('suggestions'),
                'next_question_hint': llm_response.get('next_question_hint')
            }
            
        except Exception as e:
            self._log_interaction('insight_generation', prompt, f"Error: {str(e)}")
            return {'insights': None, 'error': str(e)}

    def generate_dynamic_question(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Generate a new question based on previous responses"""
        if not self.llm_config or not self.llm_config.auto_generate_questions:
            return None
        
        prompt = self._build_question_generation_prompt(context)
        
        try:
            llm_response = self._call_llm(prompt, 'question_generation')
            
            return {
                'question_text': llm_response.get('question'),
                'question_type': llm_response.get('type', 'SHI'),
                'options': llm_response.get('options', []),
                'justification': llm_response.get('justification')
            }
            
        except Exception as e:
            self._log_interaction('question_generation', prompt, f"Error: {str(e)}")
            return None

    def determine_next_flow(self, current_responses: list) -> Dict[str, Any]:
        """Use LLM to determine optimal next question based on responses"""
        if not self.llm_config or not self.llm_config.adaptive_questioning:
            return {'next_question_id': None, 'skip_questions': []}
        
        prompt = self._build_flow_decision_prompt(current_responses)
        
        try:
            llm_response = self._call_llm(prompt, 'flow_decision')
            
            return {
                'next_question_id': llm_response.get('next_question_id'),
                'skip_questions': llm_response.get('skip_questions', []),
                'reasoning': llm_response.get('reasoning')
            }
            
        except Exception as e:
            self._log_interaction('flow_decision', prompt, f"Error: {str(e)}")
            return {'next_question_id': None, 'skip_questions': []}

    def generate_final_insights(self) -> Dict[str, Any]:
        """Generate comprehensive insights from all responses"""
        responses = self.assessment_instance.responses.filter(done=True)
        
        prompt = self._build_final_insights_prompt(responses)
        
        try:
            start_time = timezone.now()
            llm_response = self._call_llm(prompt, 'insight_generation')
            processing_time = (timezone.now() - start_time).total_seconds()
            
            # Update assessment with insights
            if llm_response.get('insights'):
                self.assessment_instance.insights = llm_response['insights']
                self.assessment_instance.score = llm_response.get('score', {})
                self.assessment_instance.save()
            
            self._log_interaction(
                'insight_generation', 
                prompt, 
                json.dumps(llm_response),
                processing_time
            )
            
            return {
                'success': True,
                'insights': llm_response.get('insights'),
                'score': llm_response.get('score'),
                'recommendations': llm_response.get('recommendations'),
                'processing_time': processing_time
            }
            
        except Exception as e:
            self._log_interaction('insight_generation', prompt, f"Error: {str(e)}")
            return {'success': False, 'error': str(e)}

    def _build_response_analysis_prompt(self, response_vector) -> str:
        """Build prompt for analyzing a single response"""
        return f"""
        Analyze this assessment response:
        
        Campaign: {self.campaign.name}
        Question: {response_vector.question.question}
        Question Type: {response_vector.question.type}
        Response: {json.dumps(response_vector.response)}
        
        Previous responses context:
        {self._get_responses_context()}
        
        Provide brief insights about this response and suggest next steps.
        
        Return JSON with: insights, suggestions, next_question_hint
        """

    def _build_question_generation_prompt(self, context: Dict[str, Any]) -> str:
        """Build prompt for generating new questions"""
        return f"""
        Generate a new assessment question based on the current context:
        
        Campaign: {self.campaign.name} ({self.campaign.type})
        Campaign Description: {self.campaign.description}
        
        Current responses:
        {self._get_responses_context()}
        
        Context: {json.dumps(context)}
        
        Generate a relevant follow-up question that will provide valuable insights.
        
        Return JSON with: question, type, options (if applicable), justification
        """

    def _build_flow_decision_prompt(self, current_responses: list) -> str:
        """Build prompt for flow decision making"""
        return f"""
        Determine the optimal next question in this assessment flow:
        
        Campaign: {self.campaign.name}
        Available questions: {self._get_available_questions()}
        
        Current responses:
        {json.dumps(current_responses, indent=2)}
        
        Determine which question should be asked next, or if any questions should be skipped.
        
        Return JSON with: next_question_id, skip_questions, reasoning
        """

    def _build_final_insights_prompt(self, responses) -> str:
        """Build prompt for final assessment insights"""
        responses_data = []
        for response in responses:
            responses_data.append({
                'question': response.question.question,
                'type': response.question.type,
                'topic': response.question.topic,
                'response': response.response
            })
        
        return f"""
        Generate comprehensive insights for this completed assessment:
        
        Campaign: {self.campaign.name} ({self.campaign.type})
        Description: {self.campaign.description}
        
        All responses:
        {json.dumps(responses_data, indent=2)}
        
        Provide:
        1. Detailed insights about the participant
        2. Scoring if applicable
        3. Recommendations for next steps
        4. Key patterns or themes identified
        
        Return JSON with: insights, score, recommendations, key_themes
        """

    def _get_responses_context(self) -> str:
        """Get context of previous responses"""
        responses = self.assessment_instance.responses.filter(done=True)[:5]  # Last 5
        context = []
        
        for response in responses:
            context.append(f"Q: {response.question.question}")
            context.append(f"A: {response.response}")
        
        return "\n".join(context)

    def _get_available_questions(self) -> list:
        """Get list of available questions"""
        questions = self.campaign.questions.all()
        return [
            {
                'id': str(q.id),
                'question': q.question,
                'type': q.type,
                'topic': q.topic,
                'order': q.order
            }
            for q in questions
        ]

    def _call_llm(self, prompt: str, interaction_type: str) -> Dict[str, Any]:
        """Call LLM API and return response"""
        # This would integrate with your existing LLM infrastructure
        # For now, returning a mock response
        from moio_platform.lib.openai_gpt_api import full_chat_reply
        
        chat = [
            {"role": "system", "content": self.llm_config.system_prompt if self.llm_config else "You are an assessment assistant."},
            {"role": "user", "content": prompt}
        ]
        
        response = full_chat_reply(
            chat=chat,
            openai_api_key=self.tenant_config.openai_api_key,
            model=self.tenant_config.openai_default_model
        )
        
        return json.loads(response)

    def _log_interaction(self, interaction_type: str, prompt: str, 
                        response: str, processing_time: Optional[float] = None):
        """Log LLM interaction for debugging and analysis"""
        LLMInteraction.objects.create(
            assessment_instance=self.assessment_instance,
            interaction_type=interaction_type,
            prompt=prompt,
            response=response,
            processing_time=processing_time
        )
