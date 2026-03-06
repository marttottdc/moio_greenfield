from chatbot.core.campaign_flow import AssessmentInstanceFlow
from assessments.models.assessment_data import AssessmentInstance, AssessmentCampaign, AssessmentQuestion, AssessmentQuestionOption, \
    AssessmentInstanceResponseVector


class AssessmentManager:

    def __init__(self, assessment_instance: AssessmentInstance):

        self.assessment_instance = assessment_instance
        self.id = assessment_instance.id
        self.status = assessment_instance.status
        self.step = assessment_instance.step
        self.campaign = AssessmentCampaign(assessment_instance.campaign)
        self.assessment_instance_flow = AssessmentInstanceFlow(assessment_instance)
        self.message = "Manager Created"

    def display_assessment(self):

        self.assessment_instance.display()
        self.message = "displaying assessment instance"

    def handle_response(self, request):
        if request.method == "POST":
            action = request.POST.get("action")
            response_id = request.POST.get("response_id")
            try:
                response_vector = AssessmentInstanceResponseVector.objects.get(id=response_id)

                self.message = f"handling {action} from {response_id} "

                response_object = []
                options = AssessmentQuestionOption.objects.filter(question=response_vector.question)

                for option in options:
                    responded_option = request.POST.get(str(option.id))
                    print(f'response for {option.option} is {responded_option}')
                    response_vector.response = {"option": option.option, "value": responded_option}
                    response_object.append(response_vector)

                response_vector.planned = False
                response_vector.done = True
                response_vector.save()

                self.assessment_instance.save()
            except Exception as e:
                print(f'{e} - {response_id}')

    def get_next_step(self):

        next_planned_question = self.assessment_instance.responses.filter(done__exact=False, planned__exact=True).first()
        if next_planned_question:
            assessment_question = AssessmentQuestion.objects.get(question=next_planned_question.question)
            options = AssessmentQuestionOption.objects.filter(question=assessment_question)

        next_question = {
            "response_vector_id": str(next_planned_question.id),
            "question": assessment_question,
            "options": options
        }

        if next_question:
            return next_question
        else:
            return None

    def get_message(self):
        return self.message
    """
    id
    question
    type
    configuration
    question_group
    optional
    order
    created_at
    description
    campaign
    """

    """
    id 
    instance
    question
    created_at
    updated_at
    planned
    mandatory
    done
    response
    """