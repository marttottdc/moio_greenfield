import ast
import os
import time

import numpy as np
import pandas as pd

from celery.exceptions import OperationalError
from django.conf import settings
from moio_platform.lib.openai_gpt_api import get_embedding
from django.db import transaction

from viewflow import fsm, this

from recruiter.core.tools import calculate_cosine_similarity
from portal.models import TenantConfiguration
from recruiter.models import JobPosting, CandidateList, Candidate, JobPostingStatus, CandidateStatus, \
    ACCEPTABLE_CANDIDATE_STATUSES
from recruiter.tasks import candidate_matching
from celery.result import AsyncResult


class JobPostingFlow(object):

    stage = fsm.State(JobPostingStatus, default=JobPostingStatus.NEW)

    def __init__(self, job_posting: JobPosting):
        self.job_posting = job_posting
        self.candidate_list = None

    @stage.setter()
    def _set_status(self, value):
        self.job_posting.status = value
        self.job_posting.save()

    @stage.getter()
    def _get_status(self):
        return self.job_posting.status

    def check_candidate_prerequisites(self, candidate, required_status):
        if candidate.recruiter_status != required_status:
            raise ValueError(
                f"Candidate {candidate.contact.fullname} does not meet the prerequisite status {required_status}")

    @stage.transition(source={JobPostingStatus.NEW, JobPostingStatus.PRESELECTING_MATCHES}, target=JobPostingStatus.PRESELECTING_MATCHES)
    def launch_search(self):

        retries = 5
        delay = 3

        for attempt in range(retries):
            try:
                job = candidate_matching.apply_async(args=[], kwargs={'tenant_id': self.job_posting.tenant.id, 'job_posting_id': self.job_posting.id, 'date_range': self.job_posting.max_age_cv}, queue=settings.MEDIUM_PRIORITY_Q)

                print(f'queued job: {job.id}')

                result = AsyncResult(job)
                while not result.ready():
                    pass

                if result.failed():
                    raise ValueError("Search failed")

                print(f"task finalizada Status{result.status} Resultado{result.result} ")

                print("Eligiendo candidatos adecuados")
                print("Estos candidatos hacen match:")
                matching_candidates = Candidate.objects.filter(
                    recruiter_posting=self.job_posting.id,
                    job_posting=self.job_posting,
                    recruiter_status=CandidateStatus.MATCHED)

                return matching_candidates

            except OperationalError as e:
                print(e)
                if attempt < retries - 1:
                    time.sleep(delay)  # Wait before retrying
                else:
                    raise ValueError("Search failed")

    @stage.transition(source=JobPostingStatus.PRESELECTING_MATCHES, target=JobPostingStatus.PERFORMING_GROUP_INTERVIEW)
    def confirm_preselection(self):

        print("Finalizando Preseleccion")
        acceptable_statuses = ACCEPTABLE_CANDIDATE_STATUSES.get(self._get_status(), [])

        print(f'acceptable_status: {acceptable_statuses}')

        viable_candidates = Candidate.objects.filter(
            recruiter_posting=self.job_posting.id,
            job_posting=self.job_posting,
            recruiter_status__in=acceptable_statuses)

        if len(viable_candidates) == 0:
            raise ValueError("Not Enough Candidates to Continue")

        else:

            for discarded_candidate in Candidate.objects.filter(recruiter_posting=self.job_posting.id, job_posting=self.job_posting).exclude(recruiter_status__in=acceptable_statuses):
                discarded_candidate.recruiter_posting = 0
                if discarded_candidate.recruiter_status != CandidateStatus.DISCARDED:
                    discarded_candidate.recruiter_status = CandidateStatus.AVAILABLE
                    print(f'Descartando: {discarded_candidate.contact.fullname}')
                    discarded_candidate.save()


    """
    @stage.transition(source=JobPostingStatus.COORDINATING_GROUP_INTERVIEW, target=JobPostingStatus.PERFORMING_GROUP_INTERVIEW)
    def confirm_group_interview_list(self):
        acceptable_statuses = [CandidateStatus.CONFIRMED_ASSISTANCE, CandidateStatus.UNAVAILABLE]

        if len(Candidate.objects.filter(recruiter_posting=self.job_posting.id, job_posting=self.job_posting).exclude(recruiter_status__in=acceptable_statuses)) > 0:
            raise ValueError("Debes Finalizar las invitaciones antes de continuar")
    """

    @stage.transition(source=JobPostingStatus.PERFORMING_GROUP_INTERVIEW, target=JobPostingStatus.CLOSING_GROUP_INTERVIEW)
    def close_group_interview(self):

        acceptable_statuses = ACCEPTABLE_CANDIDATE_STATUSES.get(self._get_status(), [])
        print(f'acceptable_status: {acceptable_statuses}')

        viable_candidates = Candidate.objects.filter(recruiter_posting=self.job_posting.id,
                                                     job_posting=self.job_posting,
                                                     recruiter_status__in=CandidateStatus.CHECK_IN_GROUP_INTERVIEW)

        if len(viable_candidates) == 0:
            raise ValueError("Not Enough Candidates to Continue")

        for candidate in Candidate.objects.filter(recruiter_posting=self.job_posting.id, job_posting=self.job_posting):
            if candidate.recruiter_status == CandidateStatus.CHECK_IN_GROUP_INTERVIEW:
                candidate.recruiter_status = CandidateStatus.EVALUATING
            else:
                candidate.recruiter_status = CandidateStatus.NO_SHOW_GROUP_INTERVIEW
            candidate.save()

    @stage.transition(source=JobPostingStatus.CLOSING_GROUP_INTERVIEW, target=JobPostingStatus.PERFORMING_INDIVIDUAL_INTERVIEWS)
    def confirm_shortlist(self):
        print("Finalizando Evaluacion Grupal")
        viable_candidates = Candidate.objects.filter(recruiter_posting=self.job_posting.id,
                                                     job_posting=self.job_posting,
                                                     recruiter_status__in=[CandidateStatus.EVALUATED_PASSED,CandidateStatus.INDIVIDUAL_INTERVIEW_STAGE])

        if len(viable_candidates) == 0:
            raise ValueError("Not Enough Candidates to Continue")

        for candidate in Candidate.objects.filter(recruiter_posting=self.job_posting.id, job_posting=self.job_posting):

            if candidate.recruiter_status == CandidateStatus.EVALUATED_PASSED:
                candidate.recruiter_status = CandidateStatus.INDIVIDUAL_INTERVIEW_STAGE
                candidate.save()

            elif candidate.recruiter_status == CandidateStatus.EVALUATED_FAILED:
                pass

            elif candidate.recruiter_status == CandidateStatus.EVALUATING:
                raise ValueError("There are candidates waiting to be evaluated")

        print("Comenzando Evaluacion Invidual")

    @stage.transition(source=JobPostingStatus.PERFORMING_INDIVIDUAL_INTERVIEWS, target=JobPostingStatus.CLOSED)
    def close_individual_interviews(self):
        print("Finalizando Evaluacion Individual")

        candidates = Candidate.objects.filter(recruiter_posting=self.job_posting.id, job_posting=self.job_posting).exclude(recruiter_status__in=[CandidateStatus.STAND_BY, CandidateStatus.HIRED])
        if len(candidates) > 0:
            raise ValueError("There are candidates waiting to be interviewed")

        viable_candidates = Candidate.objects.filter(recruiter_posting=self.job_posting.id,
                                                     job_posting=self.job_posting,
                                                     recruiter_status__in=[CandidateStatus.STAND_BY, CandidateStatus.HIRED])

        if len(viable_candidates) == 0:
            raise ValueError("Not Enough Candidates to Continue")

    @stage.transition(source=JobPostingStatus.CLOSING_INDIVIDUAL_INTERVIEWS, target=JobPostingStatus.CLOSED)
    def shortlist_results(self):
        print("Comunicando resultados")
        print("Estos candidatos tuvieron entrevistas 1 a 1")

        for candidate in Candidate.objects.filter(recruiter_posting=self.job_posting.id, job_posting=self.job_posting, recruiter_status="H"):

            print(f'{candidate.contact.fullname} contratado')

