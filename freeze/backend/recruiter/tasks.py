import ast
import os
import zipfile
from datetime import timedelta

import numpy as np
import pandas as pd
from celery import current_task
from celery.app import shared_task
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from pgvector.django import L2Distance, CosineDistance

from django.conf import settings
from crm.models import Contact, Company, Branch
from moio_platform.lib.google_maps_api import get_geocode
from moio_platform.lib.openai_gpt_api import get_embedding, get_simple_response, MoioOpenai
from portal.models import TenantConfiguration
from recruiter.core.tools import candidate_distance_to_branches_evaluation_v2
from recruiter.lib.buscojobs_api import ocr_buscojobs_cv_files, process_datos_personales, \
    process_experiencia_laboral, process_educacion, process_self_summary, process_overall_knowledge
from recruiter.lib.psigma_api import PsigmaApi
from recruiter.models import Candidate, RecruiterDocument, JobPosting, CandidateDistances, CandidateStatus
import logging

logger = logging.getLogger(__name__)


def unzip_file(doc: RecruiterDocument):

    with default_storage.open(doc.file.name, 'rb') as file:
        zip_file = zipfile.ZipFile(file)

    for file_info in zip_file.infolist():
        if file_info.filename.endswith('/'):  # Skip directories
            continue

        with zip_file.open(file_info) as extracted_file:
            file_data = extracted_file.read()  # Read the file's contents

            # Create a new RecruitmentDocument instance
            document = RecruiterDocument.objects.create(name=file_info.filename, tenant=doc.tenant, user=doc.user, source=doc.source)
            document.tags.set(doc.tags.all())

            # Save the file to the FileField
            document.file.save(file_info.filename, ContentFile(file_data))
            document.save()

            # Now the file is saved to default_storage and the instance is saved to the database


def read_pdf_file(doc: RecruiterDocument):
    try:
        cv_data = ocr_buscojobs_cv_files(doc.file.name)
        candidate_data = process_datos_personales(cv_data["Datos Personales"])
        candidate_data["name"] = cv_data["Nombre"]
        candidate_data["work_experience"] = process_experiencia_laboral(cv_data["Experiencia laboral"])
        candidate_data["education"] = process_educacion(cv_data)
        candidate_data["self_summary"] = process_self_summary(cv_data)
        candidate_data["overall_knowledge"] = process_overall_knowledge(cv_data)
        candidate_data["full_cv"] = cv_data
        candidate_data["tenant"] = doc.tenant

        try:
            contact = Contact.create_or_update(
                phone=candidate_data["phone"],
                tenant=candidate_data["tenant"],
                email=candidate_data["email"]
            )

        except Exception as e:
            doc.error += str(e)

        try:
            candidate = Candidate.objects.get(document_id=candidate_data["document"])
            candidate.full_cv_transcript = candidate_data["full_cv"]
            candidate.address = candidate_data["address"]
            candidate.postal_code = candidate_data["postal_code"]
            candidate.date_birth = candidate_data["date_of_birth"]
            candidate.work_experience = candidate_data["work_experience"]
            candidate.education = candidate_data["education"]
            candidate.self_summary = candidate_data["self_summary"]
            candidate.overall_knowledge = candidate_data["overall_knowledge"]
            candidate.reloaded = timezone.now()
            candidate.tenant = doc.tenant
            candidate.source = doc.source
            candidate.cv_file_doc = doc
            candidate.tags.set(doc.tags.all())

            print(f'inserting profile pic {cv_data["profile_pic"]}')

            try:
                image_content = ContentFile(cv_data["image_bytes"])
                candidate.profile_picture.save(cv_data["profile_pic"], image_content)

            except Exception as y:

                print(f'Exception in candidate update: {y}')
                candidate.profile_picture = None

            candidate.save()
            # print(f'Candidato: {candidate.contact.fullname} actualizado')

        except Candidate.DoesNotExist:

            candidate = Candidate(contact=contact,
                                  document_id=candidate_data["document"],
                                  postal_code=candidate_data["postal_code"],
                                  date_birth=candidate_data["date_of_birth"],
                                  address=candidate_data["address"],
                                  work_experience=candidate_data["work_experience"],
                                  education=candidate_data["education"],
                                  full_cv_transcript=candidate_data["full_cv"],
                                  overall_knowledge=candidate_data["overall_knowledge"],
                                  self_summary=candidate_data["self_summary"],
                                  tenant=doc.tenant,
                                  source=doc.source,
                                  cv_file_doc=doc)

            candidate.tags.set(doc.tags.all())

            print(f'inserting profile pic {cv_data["profile_pic"]}')

            try:
                image_content = ContentFile(cv_data["image_bytes"])
                candidate.profile_picture.save(cv_data["profile_pic"], image_content)


            except Exception as y:
                print(f'Exception in candidate create: {y}')
                candidate.profile_picture = None

            candidate.save()
            # print(f'Candidato: {candidate.contact.fullname} creado')
    except Exception as e:
        doc.error += str(e)


@shared_task(bind=True, queue=settings.LOW_PRIORITY_Q)
def import_buscojobs_candidates(self):

    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Importing Buscojobs Candidates ---> {task_id} from {q_name}')

    for tenant_config in TenantConfiguration.objects.all():
        # if tenant_config.:
        zips = RecruiterDocument.objects.filter(read=False, tenant=tenant_config.tenant, name__endswith=".zip")  # Getting list of pdf files to read
        for zip_file in zips:
            print(zip_file.file.name)
            unzip_file(zip_file)   # Open the zip file

            zip_file.read = True
            zip_file.save()

        pdfs = RecruiterDocument.objects.filter(read=False, tenant=tenant_config.tenant, name__endswith=".pdf")  # Getting list of pdf files to read
        for pdf_file in pdfs:
            print(pdf_file.file.name)
            read_pdf_file(pdf_file)

            pdf_file.read = True
            pdf_file.save()


@shared_task(bind=True, queue=settings.LOW_PRIORITY_Q)
def geocode_candidates(self):

    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Geocoding Candidates ---> {task_id} from {q_name}')


    for tenant_config in TenantConfiguration.objects.filter(google_integration_enabled=True):

        for candidate in Candidate.objects.filter(latitude__isnull=True, tenant=tenant_config.tenant):
            address = candidate.address
            if address:
                geocode_result = get_geocode(address=address, google_maps_api_key=tenant_config.google_api_key)
                latitude = geocode_result[0]["lat"]
                longitude = geocode_result[0]["lng"]
                candidate.latitude = latitude
                candidate.longitude = longitude
                candidate.save()


@shared_task(bind=True, queue=settings.LOW_PRIORITY_Q)
def branch_distance_evaluation(self):

    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Evaluating branch distances ---> {task_id} from {q_name}')

    for tenant_config in TenantConfiguration.objects.filter(google_integration_enabled=True):

        candidates_to_eval = Candidate.objects.filter(latitude__isnull=False, longitude__isnull=False, tenant=tenant_config.tenant, distance_evaluation_done=False)

        for candidate in candidates_to_eval:
            try:
                analysis = candidate_distance_to_branches_evaluation_v2(candidate, tenant_configuration=tenant_config)
                if analysis:
                    candidate.recommended_branch = analysis["reco"]
                    # print(analysis["reco"])
                    candidate.distance_to_branches = analysis["distances"]
                    # print(analysis["distances"])
                    candidate.distance_evaluation_done = True
                    candidate.save()

            except Exception as e:
                print(e)


@shared_task(bind=True, queue=settings.LOW_PRIORITY_Q)
def import_psigma_data(self):

    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Importing Psigma Score Report---> {task_id} from {q_name}')

    for tenant_config in TenantConfiguration.objects.filter(psigma_integration_enabled=True):

        psigma = PsigmaApi(username=tenant_config.psigma_user, password=tenant_config.psigma_password, token=tenant_config.psigma_token)

        for candidate in Candidate.objects.filter(recruiter_status__exact=CandidateStatus.WAITING_FOR_DATA, tenant=tenant_config.tenant):

            resultados = psigma.get_user_examinations(candidate.document_id)["contenido"]

            for resu in resultados:

                print(resu["id_usuario"], resu["nombres"], resu["apellidos"], resu["usu_cedula"], resu["usuario"])
                programaciones = resu["programaciones"]
                for prog in programaciones:
                    # print(prog)
                    # print(psigma.get_examination_status(prog["id_programacion"])["contenido"])

                    if prog["pro_estado"] == "procesado":
                        # print(prog["id_programacion"])
                        # print(psigma.get_report_url(prog["id_programacion"]))

                        detalle = psigma.get_results(prog["id_programacion"])["contenido"]
                        # print(f"Ajuste a perfil: {detalle['ajuste']}")
                        # print(" ------------- resultados ------------")
                        # categorias = detalle["resultados"]
                        candidate.psicotest_score = detalle['ajuste']
                        if candidate.recruiter_status == CandidateStatus.WAITING_FOR_DATA:
                            candidate.recruiter_status = CandidateStatus.DATA_COMPLETE

                        # for factor in categorias:
                        #    print(factor["intrafactor_nombre"], factor["puntaje"])
            candidate.save()


@shared_task(bind=True, queue=settings.MEDIUM_PRIORITY_Q)
def candidate_embedding(self):
    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Getting candidate embeddings---> {task_id} from {q_name}')

    for tenant_config in TenantConfiguration.objects.filter(openai_integration_enabled=True):

        mo = MoioOpenai(tenant_config.openai_api_key, tenant_config.openai_default_model)
        for candidate in Candidate.objects.filter(embedding__isnull=True, tenant=tenant_config.tenant).exclude(recruiter_summary__exact=""):
            print(f"Getting embedding for: {candidate.contact.fullname}")
            result = mo.get_embedding(candidate.recruiter_summary)
            if result is not None:
                candidate.embedding = result
            candidate.save()


@shared_task(bind=True, queue=settings.MEDIUM_PRIORITY_Q)
def candidate_summary(self):
    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Generating Candidate Summaries---> {task_id} from {q_name}')

    for tenant_config in TenantConfiguration.objects.filter(openai_integration_enabled=True):

        for candidate in Candidate.objects.filter(recruiter_summary__exact="", tenant=tenant_config.tenant):
            print(f"Getting candidate summary for {candidate.contact.fullname}")
            #Nombre: {candidate.contact.fullname},
            #Fecha de Nacimiento: {candidate.date_birth},
            #Ciudad: {candidate.city},
            #Direccion: {candidate.address},

            prompt = f"""
            Estos son los datos del curriculum de un candidato que estamos evaluando. 
            Hacer un resumen de 400 caracteres, dando mas importancia a las experiencias laborales mas recientes 
            y destacar los hitos educativos más importantes. 
            Datos a Evaluar:
            
            Nota de presentación: {candidate.self_summary}, 
            Experiencia laboral: {candidate.work_experience}, 
            Educación: {candidate.education}, 
            Conocimientos: {candidate.overall_knowledge}
            """
            candidate.recruiter_summary = get_simple_response(prompt, openai_api_key=tenant_config.openai_api_key, model=tenant_config.openai_default_model)
            candidate.save()


@shared_task(bind=True, queue=settings.MEDIUM_PRIORITY_Q)
def candidate_matching(self, tenant_id, job_posting_id, min_psico=70, vacant_factor=10, date_range=30):
    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Matching candidates---> {task_id} from {q_name}')

    tenant_configuration = TenantConfiguration.objects.get(tenant_id=tenant_id)

    try:
        job_posting = JobPosting.objects.get(tenant_id=tenant_id, pk=job_posting_id)

        top_n = job_posting.vacantes * vacant_factor
        branches = job_posting.branch.values_list("id")
        if branches.count() > 0:
            print(branches)
        else:
            branches = Branch.objects.filter(tenant_id=tenant_id).values_list("id")

        print(f"Buscamos {job_posting.vacantes} personas para ocupar posiciones en nuestras sucursales de {branches}, tareas a realizar {job_posting.description} ")

        if tenant_configuration.openai_integration_enabled:
            mo = MoioOpenai(tenant_configuration.openai_api_key, tenant_configuration.openai_default_model)
            job_embedding = mo.get_embedding(job_posting.description)

            if job_embedding:
                start_date = timezone.now() - timedelta(days=date_range)  # One week ago
                end_date = timezone.now()

                acceptable_status = ["A"]
                acceptable_distances = ["A"]

                available_candidates = Candidate.objects.filter(tenant_id=tenant_id, recruiter_posting=0, job_posting__isnull=True, recruiter_status__in=acceptable_status)
                available_candidates_nearby = available_candidates.filter(candidatedistances__distance_category__in=acceptable_distances, candidatedistances__branch__in=branches)
                pre_matching_candidates = available_candidates_nearby.filter(created__range=[start_date, end_date])

                exclusion_tags_count = job_posting.exclude_tags.values_list("id").count()
                inclusion_tags_count = job_posting.include_tags.values_list("id").count()

                print(f'Exclusion tags count: {exclusion_tags_count}, inclusion tags count: {inclusion_tags_count}')

                if exclusion_tags_count > 0 and inclusion_tags_count > 0:

                    pre_matching_candidates = pre_matching_candidates.exclude(tags__in=job_posting.exclude_tags.values_list("id")).filter(tags__in=job_posting.include_tags.values_list("id"))
                    print(pre_matching_candidates)

                elif exclusion_tags_count > 0:
                    pre_matching_candidates = pre_matching_candidates.exclude(tags__in=job_posting.exclude_tags.values_list("id"))
                    print(pre_matching_candidates)

                elif inclusion_tags_count > 0:
                    pre_matching_candidates = pre_matching_candidates.filter(tags__in=job_posting.include_tags.values_list("id"))
                    print(pre_matching_candidates)

                matches = pre_matching_candidates.annotate(l2_distance=L2Distance('embedding', job_embedding), cos_distance=CosineDistance('embedding', job_embedding)).order_by(L2Distance('embedding', job_embedding)).distinct()[:top_n]

                """
                matches = Candidate.objects.filter(
                    tenant_id=tenant_id,
                    recruiter_posting=0,
                    job_posting__isnull = True,
                    created__range=[start_date, end_date],
                    recruiter_status__in=acceptable_status,
                    candidatedistances__distance_category__in=acceptable_distances,
                    candidatedistances__branch__in=branches).annotate(l2_distance=L2Distance('embedding', job_embedding), cos_distance=CosineDistance('embedding', job_embedding)).order_by(L2Distance('embedding', job_embedding)).distinct()[:top_n]
                """

                if len(matches) == 0:
                    print("No Candidates Found")
                    return None

                for c in matches:

                    candidate = Candidate.objects.get(document_id=c.document_id, tenant=tenant_id)
                    candidate.recruiter_posting = job_posting_id
                    candidate.job_posting = job_posting
                    candidate.recruiter_status = "M"
                    candidate.save()

                    print(f'{c.document_id} - {c.recruiter_summary[:20]}')

        else:
            print("Candidate matching cannot work without Openai Integration")
            return None

    except JobPosting.DoesNotExist:
        raise RuntimeError("Job Posting not found")


@shared_task(bind=True, queue=settings.MEDIUM_PRIORITY_Q)
def wa_send_invitations(self, invitees):
    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Sending invitations ---> {task_id} from {q_name}')

    for inv in invitees:
        print(inv)


def reset_documents_status(tenant_id):

    cvs = RecruiterDocument.objects.filter(read=True, tenant_id=tenant_id)  # Getting list of pdf files to read
    for cv in cvs:
        print(cv.file.name)
        if cv.name.endswith(".pdf"):
            cv.read = False
            cv.error = ""
            cv.save()


def delete_candidate_distances(tenant_id):
    try:
        tenant_configuration = TenantConfiguration.objects.get(tenant_id=tenant_id)

        for candidate in Candidate.objects.filter(tenant=tenant_configuration.tenant):
            for distance in CandidateDistances.objects.filter(tenant=tenant_configuration.tenant, candidate=candidate):
                distance.delete()

            candidate.distance_evaluation_done = False
            candidate.save()

    except TenantConfiguration.DoesNotExist:
        print("No existe ese tenant")
