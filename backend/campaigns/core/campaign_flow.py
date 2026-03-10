import ast
import os
import time
import logging

from viewflow import fsm, this
from central_hub.models import TenantConfiguration

from campaigns.models import Status, Campaign
from celery.result import AsyncResult
logger = logging.getLogger(__name__)


class CampaignFlow(object):

    status = fsm.State(Status, default=Status.DRAFT)

    def __init__(self, campaign: Campaign):
        self.campaign = campaign

    @status.setter()
    def _set_status(self, value):
        self.campaign.status = value

    @status.getter()
    def _get_status(self):
        return self.campaign.status

    """
    Status.DRAFT
    Status.READY
    Status.SCHEDULED
    Status.ACTIVE
    Status.ENDED
    Status.ARCHIVED
    """

    @status.transition(source=Status.DRAFT, target=Status.READY)
    def validate(self):

        pass

    @status.transition(source=Status.READY, target=Status.SCHEDULED)
    def schedule(self):
        pass

    @status.transition(source=Status.SCHEDULED, target=Status.ACTIVE)
    def execute(self):

        pass

    @status.transition(source=Status.ACTIVE, target=Status.ENDED)
    def evaluate(self):

        pass

    @status.transition(source=Status.ENDED, target=Status.ACTIVE)
    def archive(self):
        pass

    @status.on_success()
    def _on_transition_success(self, descriptor, source, target):
        self.campaign.save()


