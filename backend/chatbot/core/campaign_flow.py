import ast
import os
import time
import numpy as np
import pandas as pd

from celery.exceptions import OperationalError

from django.db import transaction
from viewflow import fsm, this


from assessments.models.assessment_data import AssessmentInstanceStatus, AssessmentInstance, CampaignTypes


class AssessmentInstanceFlow(object):

    stage = fsm.State(AssessmentInstanceStatus, default=AssessmentInstanceStatus.NEW)

    def __init__(self, assessment_instance: AssessmentInstance):

        self.assessment_instance = assessment_instance
        if self.assessment_instance.status == AssessmentInstanceStatus.NEW:
            self.start()


    @stage.setter()
    def set_status(self, value):
        self.assessment_instance.status = value
        self.assessment_instance.save()

    @stage.getter()
    def get_status(self):
        return self.assessment_instance.status

    @stage.transition(source=AssessmentInstanceStatus.NEW, target=AssessmentInstanceStatus.READY)
    def start(self):
        try:
            questions = self.assessment_instance.campaign.questions.filter(question_group=0)

            for question in questions:
                pending_response = self.assessment_instance.responses.create(question=question, planned=True)
                pending_response.save()

            self.assessment_instance.save()

        except OperationalError:
            print(OperationalError)




