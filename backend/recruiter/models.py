import os
import uuid
from django.conf import settings

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q, UUIDField
from django.utils import timezone
from pgvector.django import VectorField

import recruiter
from crm.models import Contact, Branch, Company, Tag
from moio_platform.storage_backends import MediaStorage
from portal.context_utils import current_tenant
from portal.models import Tenant, TenantScopedModel, TenantConfiguration
from recruiter.core.ocr import ocr_generic_pdf


class RecruiterDocument(TenantScopedModel):

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to='docs/', storage=MediaStorage())
    name = models.CharField(max_length=250, null=True)
    read = models.BooleanField(default=False)
    error = models.TextField(default="")
    user = models.CharField(max_length=80, default="", null=True)
    source = models.CharField(max_length=40, default="")
    batch = models.UUIDField(editable=False, null=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name='recruiter_documents')

    class Meta:
        verbose_name = "Recruiter_Doc"

    def __str__(self):
        return self.name


class JobDescription(TenantScopedModel):

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    name = models.CharField(max_length=200, null=False)
    description = models.TextField(default="")
    rank = models.TextField(default="")
    last_update = models.DateTimeField(auto_now=True)
    salary_range = models.TextField(max_length=100, null=True, blank=True)
    embedding = models.TextField(default="")

    class Meta:
        verbose_name = "Job Description"
        verbose_name_plural = "Job Descriptions"

    def __str__(self):
        return self.name


User = get_user_model()


class JobPostingStatus(models.TextChoices):
    NEW = 'N', 'Nuevo'
    PRESELECTING_MATCHES = 'S', 'Confirmar Preselección'
    COORDINATING_GROUP_INTERVIEW = 'I', 'Finalizar Invitaciones'
    PERFORMING_GROUP_INTERVIEW = 'G', 'Iniciar Entrevista Grupal'
    CLOSING_GROUP_INTERVIEW = 'E', 'Confirmar Evaluaciones'
    PERFORMING_INDIVIDUAL_INTERVIEWS = 'U', 'Finalizar Entrevistas'
    CLOSING_INDIVIDUAL_INTERVIEWS = 'F', 'Cierre Individuales'
    CLOSED = 'C', 'Finalizado'

    def __str__(self):
        return self.label


class JobPosting(TenantScopedModel):
    jp_id = models.UUIDField(default=uuid.uuid4)
    name = models.CharField(max_length=200, null=False)
    description = models.TextField(null=False)
    created = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=40, choices=JobPostingStatus.choices, default=JobPostingStatus.NEW)
    branch = models.ManyToManyField(Branch, blank=True)
    job_description = models.ManyToManyField(JobDescription, blank=True)
    vacantes = models.IntegerField(default=1)
    start_date = models.DateTimeField(auto_now=True)
    closure_date = models.DateTimeField(null=True)
    group_interview_date = models.DateTimeField(null=True, blank=True)
    psigma_link = models.CharField(max_length=200, null=True, blank=True)
    calendar_link = models.CharField(max_length=200, null=True, blank=True)
    salary = models.IntegerField(default=0, null=True, blank=True)
    invitation_template = models.TextField(default="")
    reminder_template = models.TextField(default="")
    psicotest_template = models.TextField(default="")
    image = models.FileField(upload_to='images/', default="",blank=True, storage=MediaStorage())
    publish = models.BooleanField(default=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    updated = models.DateTimeField(auto_now=True)
    max_age_cv = models.IntegerField(default=60)
    include_tags = models.ManyToManyField(Tag, blank=True, related_name='job_postings_accepting')
    exclude_tags = models.ManyToManyField(Tag, blank=True, related_name='job_postings_refusing')

    class Meta:
        verbose_name = "Job Posting"
        verbose_name_plural = "Job Postings"

    def __str__(self):
        return self.name


class CandidateStatus(models.TextChoices):

    AVAILABLE = "A", "Available"    # default status of every candidate
    MATCHED = "M", "Matches search"     # Candidate has been matched to a search
    PRESELECTED = "P", "Preselected"      # Candidate has been preselected to participate in selection
    PENDING_DATA = "D", 'Pending data'  # Candidate has some pending data to deliver before being elegible
    DATA_COMPLETE = "C", 'Data is complete'
    INVITED_TO_GROUP_INTERVIEW = "I", 'Invited to group interview' # Candidate has been invited
    CONFIRMED_ASSISTANCE = 'G', 'Confirmed assistance'  # Candidate confirmed assistance to group interview
    CHECK_IN_GROUP_INTERVIEW = "K", 'Arrived'  # Candidate has checked in at the group interview
    NO_SHOW_GROUP_INTERVIEW = "NS", 'No Show'  # Candidate did not show to the interview
    EVALUATING = "E", 'Evaluating'
    EVALUATED = "EV", 'Evaluated'
    EVALUATED_PASSED = "VP", 'Passed Evaluation'
    EVALUATED_FAILED = "VF", 'Failed Evaluation'
    INDIVIDUAL_INTERVIEW_STAGE = 'O', 'One to one interviews'  # Candidate in one to one interview stage
    INTERVIEWING = 'OI', 'Interviewing'
    UNAVAILABLE = "U", "Unavailable"  # Candidate cannot participate in this
    STAND_BY = "S", "Selected"  # Candidate has completed successfully waiting for an open position
    HIRED = "H", "Hired"  # Candidate has been Hired
    REJECTED = "R", "Rejected"  # Candidate has failed the process
    WAITING_FOR_DATA = "W", "Waiting for data"
    DISCARDED = "X", "Discarded"

    def __srt__(self):
        return self.label


ACCEPTABLE_CANDIDATE_STATUSES = {
    JobPostingStatus.NEW: [CandidateStatus.AVAILABLE],
    JobPostingStatus.PRESELECTING_MATCHES: [CandidateStatus.MATCHED, CandidateStatus.PRESELECTED, CandidateStatus.DATA_COMPLETE, CandidateStatus.WAITING_FOR_DATA, CandidateStatus.PRESELECTED, CandidateStatus.PENDING_DATA, CandidateStatus.INVITED_TO_GROUP_INTERVIEW, CandidateStatus.CONFIRMED_ASSISTANCE, CandidateStatus.UNAVAILABLE],
    # JobPostingStatus.COORDINATING_GROUP_INTERVIEW: [CandidateStatus.DATA_COMPLETE, CandidateStatus.WAITING_FOR_DATA, CandidateStatus.PRESELECTED, CandidateStatus.PENDING_DATA, CandidateStatus.INVITED_TO_GROUP_INTERVIEW, CandidateStatus.CONFIRMED_ASSISTANCE, CandidateStatus.UNAVAILABLE],
    JobPostingStatus.PERFORMING_GROUP_INTERVIEW: [CandidateStatus.CONFIRMED_ASSISTANCE, CandidateStatus.CHECK_IN_GROUP_INTERVIEW],
    JobPostingStatus.CLOSING_GROUP_INTERVIEW: [CandidateStatus.CHECK_IN_GROUP_INTERVIEW, CandidateStatus.EVALUATING, CandidateStatus.EVALUATED],
    JobPostingStatus.PERFORMING_INDIVIDUAL_INTERVIEWS: [CandidateStatus.INDIVIDUAL_INTERVIEW_STAGE, CandidateStatus.INTERVIEWING, CandidateStatus.EVALUATED_PASSED],
    JobPostingStatus.CLOSING_INDIVIDUAL_INTERVIEWS: [CandidateStatus.INDIVIDUAL_INTERVIEW_STAGE, CandidateStatus.INTERVIEWING, CandidateStatus.EVALUATED_PASSED],
    JobPostingStatus.CLOSED: [CandidateStatus.UNAVAILABLE, CandidateStatus.STAND_BY, CandidateStatus.HIRED, CandidateStatus.REJECTED],
}


class CandidateManager(models.Manager):
    def search(self, search_word, status=CandidateStatus.AVAILABLE, job_posting_id=0):
        if status != "":
            return self.filter(
                Q(contact__fullname__icontains=search_word) |
                Q(contact__email__icontains=search_word) |
                Q(contact__phone__icontains=search_word) |
                Q(contact__whatsapp_name__icontains=search_word) |
                Q(address__icontains=search_word) |
                Q(city__icontains=search_word) |
                Q(document_id__contains=search_word), recruiter_status__in=status, job_posting_id=job_posting_id, recruiter_posting__exact=job_posting_id, tenant=current_tenant.get()
            ).distinct()

        else:
            return self.filter(
                Q(contact__fullname__icontains=search_word) |
                Q(contact__email__icontains=search_word) |
                Q(contact__phone__icontains=search_word) |
                Q(contact__whatsapp_name__icontains=search_word) |
                Q(address__icontains=search_word) |
                Q(city__icontains=search_word) |
                Q(document_id__contains=search_word) |
                Q(recruiter_summary__icontains=search_word),
                tenant=current_tenant.get()
            ).distinct()


class Candidate(TenantScopedModel):

    contact = models.ForeignKey(Contact, related_name="candidate", on_delete=models.CASCADE)
    date_birth = models.DateField(null=True, blank=True)
    address = models.CharField(max_length=400, null=True)
    city = models.CharField(max_length=200, null=True)
    state = models.CharField(max_length=200, null=True)
    postal_code = models.CharField(max_length=40, null=True)
    latitude = models.FloatField(null=True)
    longitude = models.FloatField(null=True)
    document_id = models.CharField(max_length=12)
    work_experience = models.TextField(default="")
    education = models.TextField(default="")
    tags = models.ManyToManyField(Tag, blank=True, related_name="candidates")
    applications = models.ManyToManyField(JobPosting)
    full_cv_transcript = models.TextField(default="")
    self_summary = models.TextField(default="")
    overall_knowledge = models.TextField(default="")
    distance_to_branches = models.TextField(default="")
    recommended_branch = models.CharField(max_length=200, null=True)
    psicotest_score = models.FloatField(default=None, null=True)
    created = models.DateTimeField(auto_now_add=True)
    reloaded = models.DateTimeField(auto_now_add=True, null=True)
    embedding = VectorField(dimensions=1536, null=True, blank=True)  # models.TextField(default="")
    recruiter_summary = models.TextField(default="")
    recruiter_posting = models.IntegerField(default=0)
    recruiter_status = models.CharField(max_length=30, choices=CandidateStatus.choices,  default=CandidateStatus.AVAILABLE)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    source = models.CharField(max_length=40, default="")
    distance_evaluation_done = models.BooleanField(default=False)
    profile_picture = models.ImageField(upload_to="profile_pics/", null=True, storage=MediaStorage())
    cv_file_doc = models.ForeignKey(RecruiterDocument, on_delete=models.SET_NULL, null=True, blank=True)
    code = UUIDField(editable=False, null=True)
    job_posting = models.ForeignKey(JobPosting, on_delete=models.SET_NULL, null=True, blank=True, related_name="candidates")

    objects = CandidateManager()

    class Meta:
        verbose_name = "Candidate"
        verbose_name_plural = "Candidates"
        constraints = [
            models.UniqueConstraint(fields=['document_id', 'tenant'], name='unique_documentId_tenant')
        ]

    def __str__(self):
        return self.contact.fullname

    def discard(self):
        self.recruiter_status = CandidateStatus.AVAILABLE
        self.recruiter_posting = 0
        self.job_posting = None

        self.save()

    def hard_discard(self):
        self.recruiter_status = CandidateStatus.DISCARDED
        self.recruiter_posting = 0
        self.job_posting = None
        self.save()

    def hire(self):
        self.recruiter_status = CandidateStatus.HIRED
        self.save()

    def stand_by(self):
        self.recruiter_status = CandidateStatus.STAND_BY
        self.save()

    def reject(self):
        self.recruiter_status = CandidateStatus.REJECTED
        self.save()

    def preselect(self):
        self.recruiter_status = CandidateStatus.PRESELECTED
        self.save()

    def pending_data(self):
        self.recruiter_status = CandidateStatus.PENDING_DATA
        self.save()

    def evaluate(self):
        self.recruiter_status = CandidateStatus.EVALUATED
        self.save()

    def data_completed(self):
        self.recruiter_status = CandidateStatus.DATA_COMPLETE
        self.save()

    def invite_to_group_interview(self):
        self.recruiter_status = CandidateStatus.INVITED_TO_GROUP_INTERVIEW
        self.save()

    def confirm_participation_group_interview(self):
        self.recruiter_status = CandidateStatus.CONFIRMED_ASSISTANCE
        self.save()

    def request_data(self):
        self.recruiter_status = CandidateStatus.WAITING_FOR_DATA
        self.save()

    def check_in(self):
        self.recruiter_status = CandidateStatus.CHECK_IN_GROUP_INTERVIEW
        self.save()

    def no_show(self):
        self.recruiter_status = CandidateStatus.NO_SHOW_GROUP_INTERVIEW
        self.save()

    def confirm_evaluation(self):
        self.recruiter_status = CandidateStatus.EVALUATED
        self.save()

    def individual_interview_stage(self):
        self.recruiter_status = CandidateStatus.INDIVIDUAL_INTERVIEW_STAGE
        self.save()

    def interview(self):
        self.recruiter_status = CandidateStatus.INTERVIEWING
        self.save()

    def unavailable(self):
        self.recruiter_status = CandidateStatus.UNAVAILABLE
        self.save()

    def no_response(self):
        self.recruiter_status = CandidateStatus.UNAVAILABLE
        self.save()

    def rejected(self):
        self.recruiter_status = CandidateStatus.UNAVAILABLE
        self.save()

    def passed_group_evaluation(self):
        self.recruiter_status = CandidateStatus.EVALUATED_PASSED
        self.save()

    def failed_group_evaluation(self):
        self.recruiter_status = CandidateStatus.EVALUATED_FAILED
        self.save()


class CandidateList(TenantScopedModel):

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    posting_id = models.IntegerField(null=False)
    job_posting = models.ForeignKey(JobPosting, on_delete=models.SET_NULL, null=True)
    candidate_document = models.CharField(max_length=12, null=True, default="")
    candidate = models.ForeignKey(Candidate, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=40, default="nuevo")
    created = models.DateTimeField(auto_now_add=True)


class RecruiterConfiguration(TenantScopedModel):

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, default="")
    hiringroom_client_id = models.CharField(max_length=200, null=True, default="")
    hiringroom_client_secret = models.CharField(max_length=200, null=True, default="")
    hiringroom_username = models.CharField(max_length=200, null=True, default="")
    hiringroom_password = models.CharField(max_length=200, null=True, default="")
    psigma_user = models.CharField(max_length=200, null=True, default="")
    psigma_password = models.CharField(max_length=200, null=True, default="")
    psigma_token = models.CharField(max_length=200, null=True, default="")
    psigma_url = models.CharField(max_length=200, null=True, default="")

    def __str__(self):
        return f"Recruiter config {self.company.name}"


class Employee(TenantScopedModel):
    EMPLOYEE_STATUS_OPTIONS = [("A", "active"), ("R", "resigned"), ("F", "fired"), ("D", "deceased"), ("U", "unknown")]
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    document_id = models.CharField(max_length=12)
    hired = models.DateField(null=False)
    branch = models.CharField(max_length=100, null=True, blank=True)
    company = models.CharField(max_length=100, null=True, blank=True)
    job = models.CharField(max_length=100, null=True, blank=True)
    status = models.CharField(max_length=100, choices=EMPLOYEE_STATUS_OPTIONS,  default="A")
    exit = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Employee"
        verbose_name_plural = "Employees"
        constraints = [
            models.UniqueConstraint(fields=['document_id', 'tenant'], name='employee_unique_documentId_tenant')
        ]


class CandidateDistances(TenantScopedModel):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    distance = models.FloatField(null=True, blank=True)
    distance_category = models.CharField(max_length=30, null=True, blank=True)
    duration = models.CharField(max_length=50, null=True, blank=True)
    duration_category = models.CharField(max_length=30, null=True, blank=True)


class CandidateEvaluation(TenantScopedModel):

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE)
    job_posting = models.ForeignKey(JobPosting, on_delete=models.CASCADE)
    comment = models.CharField(max_length=240, default="", blank=True)
    overall_approve = models.BooleanField(default=False)
    date = models.DateTimeField(null=True, default=timezone.now)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)


class CandidateEvaluationScore(models.Model):

    evaluation = models.ForeignKey(CandidateEvaluation, related_name="scores", on_delete=models.CASCADE)
    topic = models.CharField(max_length=40, default="default")
    category = models.CharField(max_length=40)
    score = models.CharField(max_length=40)

    class Meta:
        unique_together = ('evaluation', 'category')

    def __str__(self):
        return f'{self.evaluation.candidate.contact.fullname} - {self.topic} - {self.category} - {self.score}'


class CandidateInterviewNotes(models.Model):

    evaluation = models.ForeignKey(CandidateEvaluation, related_name="notes", on_delete=models.CASCADE)
    date = models.DateTimeField(default=timezone.now)
    note = models.TextField()
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)


class CandidateDraft(models.Model):

    fullname = models.CharField(max_length=200, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    whatsapp = models.CharField(max_length=20, null=True, blank=True)

    date_birth = models.DateField(null=True, blank=True)
    address = models.CharField(max_length=400, null=True)
    city = models.CharField(max_length=200, null=True)
    state = models.CharField(max_length=200, null=True)
    postal_code = models.CharField(max_length=40, null=True)

    document_id = models.CharField(max_length=12)
    work_experience = models.TextField(default="")
    education = models.TextField(default="")
    tags = models.ManyToManyField(Tag, blank=True, related_name="candidate_drafts")

    full_cv_transcript = models.TextField(default="")
    self_summary = models.TextField(default="")
    overall_knowledge = models.TextField(default="")

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    source = models.CharField(max_length=40, default="")
    profile_picture = models.ImageField(upload_to="profile_pics/", null=True, storage=MediaStorage())
    cv_file_doc = models.ForeignKey(RecruiterDocument, on_delete=models.SET_NULL, null=True, blank=True)

    @classmethod
    def create_from_ocr(cls, config: TenantConfiguration, document=None, tags=None, source="" ):
        try:
            # Extract data from the file using the OCR function.
            extracted_data = ocr_generic_pdf(config, file=document.file)
            candidate_data = extracted_data[0]
            profile_img = extracted_data[1]


            # Assuming extracted_data returns a dictionary with relevant fields.

            # preferencias: list[str]
            fullname = candidate_data.name
            email = candidate_data.email
            phone = candidate_data.phone
            whatsapp = candidate_data.whatsapp
            date_birth = None if getattr(candidate_data, 'date_of_birth', '') == '' else candidate_data.date_of_birth
            address = candidate_data.address
            # city = candidate_data.city
            # state = candidate_data.state
            postal_code = candidate_data.postal_code
            document_id = candidate_data.cedula
            work_experience = candidate_data.work_experience
            education = candidate_data.education
            #full_cv_transcript = candidate_data.full_cv_transcript
            self_summary = candidate_data.summary
            overall_knowledge = candidate_data.skills

            # Create the CandidateDraft instance with the extracted data.
            candidate_draft = cls.objects.create(
                tenant=config.tenant,
                fullname=fullname,
                email=email,
                phone=phone,
                whatsapp=whatsapp,
                date_birth=date_birth,
                address=address,
                city="",
                state="",
                postal_code=postal_code,
                document_id=document_id,
                work_experience=work_experience,
                education=education,
                full_cv_transcript="",
                self_summary=self_summary,
                overall_knowledge=overall_knowledge,
                source=source,
            )

            candidate_draft.cv_file_doc = document
            candidate_draft.save()
            # Add tags if provided.
            if tags:
                candidate_draft.tags.set(tags)

            return candidate_draft

        except KeyError as e:
            raise ValueError(f"Missing required field in OCR data: {e}")
        except Exception as e:
            raise RuntimeError(f"Error creating candidate draft from OCR: {str(e)}")
