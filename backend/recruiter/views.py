import json
import os
import time
import uuid
from django.conf import settings
import pandas as pd
from celery.exceptions import OperationalError
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponseRedirect, JsonResponse, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from crm.models import Branch, Contact, Tag
from portal.context_utils import current_tenant
from portal.models import TenantConfiguration, Tenant, AppMenu
from recruiter.core.flows import JobPostingFlow
from recruiter.core.tools import insert_tags
from recruiter.core.ocr import ocr_generic_pdf
from recruiter.filters import CandidateFilter
from recruiter.forms import JobPostingForm, LandingSearchForm, JobPostingMessageTemplates
from recruiter.models import RecruiterDocument, JobPosting, Candidate, CandidateList, JobPostingStatus, \
    ACCEPTABLE_CANDIDATE_STATUSES, CandidateEvaluation, CandidateEvaluationScore, CandidateStatus, \
    CandidateInterviewNotes, CandidateDraft
from recruiter.tasks import candidate_matching, import_buscojobs_candidates
from recruiter.core.charting import plot_clusters

# from recruiter.forms import RecruiterDocumentForm
# Create your views here.


@login_required
def recruiter_dashboard(request):
    tenant = current_tenant.get()

    context = {
        "available_candidates": "",
        "in_proces_candidates": "",
        "hired_candidates": "",
        "stand_by_candidates": "",
        "candidates_with_psigma": "",
        "candidates_geocoded": "",
        "candidates_summarized": "",
        'tenant': tenant.id,
        'GOOGLE_MAPS_API_KEY': TenantConfiguration.objects.get(tenant=current_tenant.get()).google_api_key
        }

    if request.htmx:
        return render(request, 'recruiter/dashboard.html', context=context)
    else:
        context["page_name"] = 'recruiter/dashboard.html'
        return render(request, 'partials/full_page.html', context)


@login_required
def recruiter_dashboard_posting_list(request):
    tenant = current_tenant.get()

    context = {
        "postings": JobPosting.objects.all().order_by("-updated"),
        'tenant': tenant.id
        }

    return render(request, 'recruiter/partials/job_posting_list.html', context=context)


def landing_page(request):
    if request.method == "POST":
        form = LandingSearchForm(request.POST)
        if form.is_valid():
            results = f"este es tu resultado: {form.cleaned_data['search_term']}"
            return render(request, 'recruiter/oportunidades.html', {"form": form, "results": results})
        else:
            return render(request, 'recruiter/oportunidades.html', {"form": form})

    else:
        form = LandingSearchForm()
        return render(request, 'recruiter/oportunidades.html', {"form": form})


@login_required
@require_POST
@csrf_exempt
def candidate_update(request):

    candidate_id = request.POST.get('candidate_id')
    new_status = request.POST.get('new_status')
    job_posting_id = request.POST.get('job_posting')

    print(f"Cambiar {candidate_id} a {new_status} in {job_posting_id}")
    User = get_user_model()
    tenant = User.objects.get(username=request.user.username).tenant
    candidate = Candidate.objects.get(document_id=candidate_id)
    job_posting = JobPosting.objects.get(id=job_posting_id)

    if new_status == "convocar":
        candidate.recruiter_posting = job_posting_id
        candidate.job_posting = job_posting
        candidate.recruiter_status = "P"
        candidate.save()
    else:
        candidate.recruiter_posting = 0
        candidate.job_posting = job_posting
        candidate.recruiter_status = "M"
        candidate.save()

    try:
        listed_candidate = CandidateList.objects.filter(posting_id=job_posting_id).get(candidate_document=candidate_id)

        if new_status == "convocar":
            listed_candidate.status = new_status
            listed_candidate.candidate = candidate
            listed_candidate.tenant = tenant
            listed_candidate.save()

        else:
            listed_candidate.delete()

    except CandidateList.DoesNotExist:

        if new_status == "convocar":
            candidate_added = CandidateList(candidate_document=candidate_id, candidate=candidate, posting_id=job_posting_id, status=new_status, tenant=tenant)
            candidate_added.save()

    ####################
    for c in CandidateList.objects.filter(posting_id=job_posting):
        print(c.candidate.contact.fullname, c.status, c.posting_id)

    return JsonResponse({'status': 'success'})


@login_required
def candidate_status_update(request, pk):
    if request.method == "POST":

        selected_value = request.POST.get('invitation-status')
        job_posting_id = request.POST.get('job_posting_id')

        candidate_list_item = CandidateList.objects.get(posting_id=job_posting_id, candidate__exact=pk)
        candidate_list_item.status = selected_value
        candidate_list_item.save()
        print(candidate_list_item.status)

        return HttpResponse(status=204, headers={
                    'HX-Trigger': json.dumps({
                        "showMessage": f"Candidato {pk} status {selected_value}."
                    })
            })


@login_required()
def carga_cvs(request):

    if request.method == "POST":
        if request.POST.get('action') == 'save-metadata':
            batch = uuid.uuid4()
            tags = request.POST.get('tags', '')
            source = request.POST.get('source', '')

            context = {
                "tags": tags,
                "source": source,
                "batch": str(batch),
                "content_page": 'recruiter/buscojobs_cvs_upload_dropzone.html',
                "page_title": "Seleccionar Cvs"
            }
            return render(request, template_name='recruiter/buscojobs_cvs_upload_dropzone.html', context=context)

        else:
            print("getting files")
            # files = request.FILES.getlist('files')  # 'file' matches the paramName in Dropzone config

            batch = request.POST.get('batch')
            tags = request.POST.get('tags', '')
            source = request.POST.get('source', '')
            tag_list = None
            if tags != '':
                tag_list = tags.split(',')

            tenant = current_tenant.get()
            files = request.FILES
            i = 0
            key = f'files[{i}]'
            while files.get(key):
                file = files.get(key)
                i = i + 1
                key = f'files[{i}]'

                document = RecruiterDocument.objects.create(file=file,
                                                            name=file.name.lower(),
                                                            tenant=tenant,
                                                            batch=batch,
                                                            source=source,
                                                            user=request.user.username
                                                            )
                print(document.name, tags, batch)
                if tag_list:
                    insert_tags(document, tag_list=tag_list, tenant=tenant)

                document.save()

            job = import_buscojobs_candidates.apply_async(queue=settings.LOW_PRIORITY_Q)
            return HttpResponse(
                status=204,
                headers={
                    'HX-Trigger': json.dumps({
                        "showMessage": "Archivos Cargados"
                    })
                })

    else:
        try:
            context = {
                "content_page": 'recruiter/buscojobs_cvs_upload_metadata.html',
                "page_title": "Cargar Cvs"
            }
            return render(request, template_name='partials/modal_factory.html', context=context)

        except Exception as e:
            # Log the error or handle it in some other way
            # For example, you could return a custom error page
            print(e)
            return render(request, template_name='500.html')


@login_required()
def confirm_cv_load(request):
    tenant = current_tenant.get()
    documents = RecruiterDocument.objects.filter(tenant=tenant,
                                                 user=request.user.username,
                                                 read__exact=False)

    context = {
        "documents": documents,
        "content_page": "recruiter/buscojobs_cvs_upload_confirmation.html",
        "page_title": "Cargas"

    }

    return render(request, template_name='recruiter/buscojobs_cvs_upload_confirmation.html', context=context)


@login_required()
def import_generic_cv(request):

    tenant = current_tenant.get()
    config = tenant.configuration.first()

    if request.method == "POST":

        if 'cv_file' in request.FILES:

            cv = request.FILES['cv_file']

            batch = request.POST.get('batch')
            tags = request.POST.get('tags', '')
            source = request.POST.get('source', 'generic')
            tag_list = None
            if tags != '':
                tag_list = tags.split(',')

            document = RecruiterDocument.objects.create(file=cv,
                                                        name=cv.name.lower(),
                                                        tenant=tenant,
                                                        batch=batch,
                                                        source=source,
                                                        user=request.user.username
                                                        )
            print(document.name, tags, batch, source)
            if tag_list:
                insert_tags(document, tag_list=tag_list, tenant=tenant)

            document.save()

            try:
                draft = CandidateDraft.create_from_ocr(config, document=document)
                draft.save()

                print(draft.fullname, draft.self_summary)

                context = {
                    "candidate": draft,
                    'content_page': 'recruiter/partials/candidate_load_data_validation_form.html',
                    'page_title': 'Confirmar datos'
                }
                return render(request, template_name='partials/modal_factory.html', context=context)

            except Exception as e:
                print(e)
                return render(request, template_name='500.html')

    context = {
        'content_page': 'recruiter/load_cv.html',
        'page_title': 'Import CV'
    }
    return render(request, template_name='partials/modal_factory.html', context=context)


@login_required()
def load_employees(request):
    tenant = current_tenant.get()
    config = tenant.configuration.first()

    if request.method == "POST":
        candidate = None
        if 'employees_file' in request.FILES:
            data_file = request.FILES['employees_file']
            file_content_type = data_file.content_type

        context = {
            "employees": None,
            "content_page":'recruiter/load_employees.html',
            "page_title": "Importar Empleados"
        }

        return render(request, template_name='recruiter/partials/employees_load_data_validation_form.html', context=context)

    context = {
        "employees": None,
        "content_page": 'recruiter/load_employees.html',
        "page_title": "Importar Empleados"
    }

    return render(request, template_name='partials/modal_factory.html', context=context)


@login_required()
def upload_cvs_stats(request):

    documents = RecruiterDocument.objects.filter(read=False)
    pdf_count = documents.filter(name__contains="pdf", ).count()
    zip_count = documents.filter(name__contains="zip", ).count()

    return render(request, template_name='recruiter/partials/cvs_upload_stats.html', context={'pdf_count': pdf_count, 'zip_count': zip_count})


@login_required()
def manual_selection(request):

    candidate_list = Candidate.objects.order_by("created")[:10]
    candidates = []
    for candidate in candidate_list:
        item = {
            "pk": candidate.pk,
            "fullname": candidate.contact.fullname,
            "document": candidate.document_id,
            "phone": candidate.contact.phone,
            "recruiter_summary": candidate.recruiter_summary,
            "email": candidate.contact.email,
            "psigma_score": candidate.psicotest_score,
            "address": candidate.address,
            "branches": candidate.recommended_branch
        }
        candidates.append(item)

    context = {"candidates": candidates}

    return render(request, 'recruiter/partials/dashboard_kpis.html', context=context)


@login_required
def configuration(request):
    if request.user.is_authenticated:
        if request.method == "POST":
            form = JobPostingForm(request.POST)
            if form.is_valid():
                new_posting = JobPosting(
                    name=form.cleaned_data["name"],
                    start_date=form.cleaned_data["start_date"],
                    group_interview_date=form.cleaned_data["group_interview_date"],
                    closure_date=form.cleaned_data["closure_date"],
                    branch=form.cleaned_data["branch"],
                    description=form.cleaned_data["description"],
                    created=timezone.now()
                )
                User = get_user_model()
                new_posting.user = User.objects.get(username=request.user.username)
                new_posting.tenant = new_posting.user.tenant
                new_posting.save()

            else:
                print(f"no valido {form.errors}")

            return HttpResponseRedirect("/recruiter/dashboard")
        else:
            return render(request, 'recruiter/admin/configuration.html', {})

    else:
        messages.success(request, "You Must Be Logged In...")
        return redirect('account/login')


@csrf_exempt
def receive_psigma_webhook(request):

    if request.method == "GET":
        return HttpResponseBadRequest()

    elif request.method == "POST":

        try:
            body = json.loads(request.body)
            print("Payload received")

            print(body)

            return HttpResponse("EVENT_RECEIVED", status=200)

        except Exception as e:
            print(e)
            return HttpResponseBadRequest()


@login_required
def candidate_search(request):

    if request.method == "POST":

        search_word = request.POST.get("search")
        job_posting_id = request.POST.get("job_posting")
        job_posting = JobPosting.objects.get(pk=job_posting_id)

        jp_flow_control = JobPostingFlow(job_posting=job_posting)

        acceptable_statuses = ACCEPTABLE_CANDIDATE_STATUSES.get(jp_flow_control._get_status(), [])

        candidates = Candidate.objects.search(search_word, acceptable_statuses, job_posting.id)

        return render(request, template_name='recruiter/partials/job_posting_candidate_list.html', context={'candidates': candidates, "job_posting": job_posting})


@login_required
def candidates_list(request):
    tenant = current_tenant.get()
    action = request.GET.get('action')
    print(f"get requested {request.GET}")

    candidates_filter = CandidateFilter(
        request.GET,
        queryset=Candidate.objects.filter(tenant=tenant).order_by("-document_id")
    )

    paginator = Paginator(candidates_filter.qs, 12)
    page_number = request.GET.get('page_number', 1)
    candidates_page = paginator.page(page_number)

    context = {
        'candidates': candidates_page,
        'filter': candidates_filter,
    }

    if action == "load_more" or action == "filter":
        print("loading more..")
        return render(request, template_name='recruiter/partials/candidate_list.html', context=context)

    return render(request, template_name='recruiter/candidates.html', context=context)


@login_required
def candidate_page(request, pk):

    candidate = Candidate.objects.get(pk=pk)
    job_posting = JobPosting.objects.get(pk=candidate.recruiter_posting)
    content_page = "recruiter/candidate_page.html"

    if request.htmx:
        return render(request, template_name="recruiter/partials/modal_factory.html", context={'candidate': candidate, 'job_posting': job_posting, "content_page": content_page, "page_title": candidate.contact.fullname})

    else:
        return render(request, template_name="recruiter/candidate_page_full.html", context={'candidate': candidate, 'job_posting': job_posting})


@login_required
def candidate_status(request, jp_id, pk):

    candidate = Candidate.objects.get(pk=pk)
    job_posting = JobPosting.objects.get(jp_id=jp_id)

    if request.method == "POST":
        action = request.POST.get("action")
        print(action)
        if action == "preselect" and candidate.psicotest_score is None:
            action = "pending_data"

        try:
            set_status = getattr(candidate, action)
            set_status()

            print(candidate.recruiter_status)

            if action == "discard":
                return JsonResponse(data={}, headers={
                    'HX-Trigger': json.dumps({
                        "showMessage": f"Candidato {candidate.contact.fullname} descartado"
                    })
                })

            if action == "hard_discard":
                return JsonResponse(data={}, headers={
                    'HX-Trigger': json.dumps({
                        "showMessage": f"Candidato {candidate.contact.fullname} eliminado"
                    })
                })

            if job_posting.status in [JobPostingStatus.NEW, JobPostingStatus.PRESELECTING_MATCHES, JobPostingStatus.COORDINATING_GROUP_INTERVIEW, JobPostingStatus.PERFORMING_GROUP_INTERVIEW]:
                return render(request, template_name="recruiter/partials/candidate_card_row.html", context={"candidate": candidate, "job_posting": job_posting})

            else:
                return render(request, template_name="recruiter/partials/candidate_card_thin.html", context={"candidate": candidate, "job_posting": job_posting})

        except Exception as e:
            return JsonResponse(data={}, headers={
                'HX-Trigger': json.dumps({
                    "showMessage": f"{e}"
                })
            })


@login_required
def candidate_discard(request, jp_id, pk):

    candidate = Candidate.objects.get(pk=pk)
    job_posting = JobPosting.objects.get(jp_id=jp_id)

    return render(request, template_name='recruiter/partials/candidate_discard_type.html', context={"candidate": candidate, "job_posting": job_posting})


@login_required
def get_candidate_markers():

    candidate_locations = Candidate.objects.all()
    markers = []
    for candidate in candidate_locations:
        m = {
            'lat': str(candidate.latitude),
            'lng': str(candidate.longitude),
            'title': candidate.contact.fullname
        }
        # print(m)
        markers.append(m)

    return json.dumps(markers)

"""
def get_candidate_clusters(tenant):
    # Retrieve candidate embeddings filtered by tenant and exclude empty embeddings
    candidates = Candidate.objects.all().exclude(embedding__exact="").values_list('id', 'embedding')

    # Convert embeddings to numpy arrays of floats, handling errors gracefully
    embeddings = []
    failed_candidates = []
    for candidate_id, embedding in candidates:
        try:
            embeddings.append(np.array(ast.literal_eval(embedding), dtype=float))
        except (ValueError, SyntaxError) as e:
            failed_candidates.append(candidate_id)
            print(f"Error parsing embedding for candidate {candidate_id}: {e}")
            continue

    # Check if there are valid embeddings to process
    if not embeddings:
        return {"error": "No valid embeddings found."}

    # Perform KMeans clustering
    matrix = np.vstack(embeddings)
    n_clusters = 4
    kmeans = KMeans(n_clusters=n_clusters, init='k-means++', random_state=42)
    kmeans.fit(matrix)

    # Dimensionality Reduction to 3D for Three.js visualization
    pca = PCA(n_components=3)
    reduced_data = pca.fit_transform(matrix)

    # Prepare data for Three.js
    points = reduced_data.tolist()
    clusters = kmeans.labels_.tolist()
    visualization_data = [{
        "x": float(point[0]),
        "y": float(point[1]),
        "z": float(point[2]),
        "cluster": cluster
    } for point, cluster in zip(points, clusters)]

    # Log failed_candidates if necessary
    return json.dumps(visualization_data)
"""


@login_required
def data_importer(request):

    imports = [
       {
           'title': 'Current Employees',
           'template_link': '/media/templates/current_employees_template.xlsx',
           'modal_id': 'current_employees_modal'
       },
       {
           'title': 'Products Import',
           'template_link': '/media/templates/products_template.xlsx',
           'modal_id': 'products_modal',
       },
       {
           'title': 'Branches Import',
           'template_link': '/media/templates/branches_template.xlsx',
           'modal_id': 'branches_modal',
       },
       {
           'title': 'Leads Import',
           'template_link': '/media/templates/leads_template.xlsx',
           'modal_id': 'leads_modal',
       }
    ]
    if request.method == "POST":

        uploaded_file = request.FILES.get('file')
        if uploaded_file:

            df = pd.read_excel(uploaded_file)

            user_domain = request.user.email.split("@")[1]
            tenant = Tenant.objects.get(domain=user_domain)
            # import_branches(df, tenant)

        else:
            print("no file")
    return render(request, 'admin/import_data.html', {'imports': imports})


@login_required
def job_posting_add(request):

    if request.method == "POST":
        form = JobPostingForm(request.POST, request.FILES)

        if form.is_valid():
            job_posting = form.save()

            response = render(request, template_name='recruiter/dashboard.html')

            return response

        else:
            return HttpResponse(
                status=204,
                headers={
                    'HX-Trigger': json.dumps({
                        "jobPostingAdded": None,
                        "showMessage": f"Error {form.errors}"
                    })
                })

    else:

        UserModel = get_user_model()
        user = UserModel.objects.get(email=request.user.email)
        tenant = user.tenant
        print(tenant)

        initial_job_posting_form = JobPostingForm(initial={'tenant': tenant, 'user': request.user, 'max_age_cv': 45})
        initial_job_posting_form.branches = Branch.objects.filter(tenant=tenant)
        initial_job_posting_form.include_tags = Tag.objects.filter(tenant=tenant)
        initial_job_posting_form.exclude_tags = Tag.objects.filter(tenant=tenant)

        context = {
            'create_posting_form': initial_job_posting_form,
            'content_page': "recruiter/partials/job_posting_form.html",
            'page_title': 'Crear Llamado',
                   }
        return render(request, "partials/modal_factory.html", context=context )


@login_required
def job_posting_details(request, jp_id):

    try:
        job_posting = JobPosting.objects.get(jp_id=jp_id)
        jp_flow_control = JobPostingFlow(job_posting)

        if jp_flow_control._get_status() == JobPostingStatus.NEW:
            jp_flow_control.launch_search()

        acceptable_statuses = ACCEPTABLE_CANDIDATE_STATUSES.get(jp_flow_control._get_status(), [])

        print(f'JobPosting Status is {jp_flow_control._get_status()} accepting: {acceptable_statuses}')

        candidates = Candidate.objects.filter(recruiter_status__in=acceptable_statuses,
                                              job_posting=job_posting,
                                              recruiter_posting=job_posting.pk).order_by('recruiter_status')

    except JobPosting.DoesNotExist:
        job_posting = None

    except JobPosting.MultipleObjectsReturned:
        print("job postings con jp_id duplicada")
        job_posting = None

    context = {
        "job_posting": job_posting,
        "candidates": candidates,
        "job_posting_update_form": JobPostingForm(instance=job_posting),
    }
    if request.htmx:
        return render(request, 'recruiter/job_posting.html', context)
    else:
        context["page_name"] = 'recruiter/job_posting.html'
        return render(request, 'partials/full_page.html', context)


@login_required()
def job_posting_action(request, jp_id):

    if request.method == "POST":

        next_step = request.POST.get("next_step")

        try:
            job_posting = JobPosting.objects.get(jp_id=jp_id)

        except JobPosting.DoesNotExist:

            job_posting = None
            candidates = None

        try:
            jp_flow_control = JobPostingFlow(job_posting)
            flow_step = getattr(jp_flow_control, next_step)
            flow_step()
            print("status actual", jp_flow_control._get_status())

        except Exception as e:
            return HttpResponse(status=204, headers={
                'HX-Trigger': json.dumps({
                    "showMessage": f"FAILED: {e}"
                })
            })

    else:
        job_posting = JobPosting.objects.get(jp_id=jp_id)
        jp_flow_control = JobPostingFlow(job_posting)

        if jp_flow_control._get_status() == JobPostingStatus.NEW:
            jp_flow_control.launch_search()
            print("status actual", jp_flow_control._get_status())

    acceptable_statuses = ACCEPTABLE_CANDIDATE_STATUSES.get(jp_flow_control._get_status(), [])

    print(f'JobPosting Status is {jp_flow_control._get_status()} accepting: {acceptable_statuses}')

    candidates = Candidate.objects.filter(recruiter_status__in=acceptable_statuses, recruiter_posting=job_posting.pk, job_posting=job_posting).order_by('recruiter_posting')

    eval_categories = ['equipo', 'escucha', 'elocuente', 'resolutivo', 'presencia']
    return render(request=request, template_name="recruiter/job_posting.html", context={"job_posting": job_posting, "candidates": candidates, "eval_categories": eval_categories})


@login_required()
def job_posting_statistics(request, jp_id):
    tenant = current_tenant.get()
    job_posting = JobPosting.objects.get(jp_id=jp_id)
    candidates = Candidate.objects.filter(recruiter_posting=job_posting.pk, job_posting=job_posting)
    candidate_statistics = []
    for possible_status in CandidateStatus:
        total_candidates = candidates.filter(tenant=tenant).count()
        candidates_status = {
            "status": possible_status,
            "value": candidates.filter(recruiter_status__exact=possible_status).count()
        }
        if candidates_status["value"] > 0:
            candidate_statistics.append(candidates_status)

    return render(request, template_name='recruiter/partials/job_posting_candidates_stats.html', context={'stats': candidate_statistics, 'vacantes': job_posting.vacantes, 'total_candidates': total_candidates})


# ===================== EVALUACIONES ==========================


@login_required()
def register_candidate_evaluation(request, jp_id, pk):
    eval_categories = ['equipo', 'escucha', 'elocuente', 'resolutivo', 'presencia']

    candidate = Candidate.objects.get(pk=pk)
    job_posting = JobPosting.objects.get(jp_id=jp_id)

    try:
        candidate_evaluation = CandidateEvaluation.objects.get(candidate=candidate, job_posting=job_posting)

    except CandidateEvaluation.DoesNotExist:
        candidate_evaluation = CandidateEvaluation.objects.create(candidate=candidate, job_posting=job_posting, tenant=job_posting.tenant)
        candidate_evaluation.date = timezone.now()
        candidate_evaluation.user = request.user
        candidate_evaluation.save()

    if request.method == "POST":

        # Get the new comment from the POST request
        new_comment = str(request.POST.get("group_eval_comments", "")).strip()

        # Concatenate the existing comment with the new comment
        if new_comment != "":
            candidate_evaluation.comment = new_comment

        if request.POST.get("psy_eval"):
            score = request.POST.get("psy_eval")
            try:
                psy_score = CandidateEvaluationScore.objects.get(evaluation=candidate_evaluation, category="psy_eval")
                psy_score.score = score
            except CandidateEvaluationScore.DoesNotExist:
                psy_score = CandidateEvaluationScore.objects.create(evaluation=candidate_evaluation,
                                                                    topic="psychological",
                                                                    category="psy_eval",
                                                                    score=score)

            psy_score.save()

        for category in eval_categories:
            if request.POST.get(category):
                score = request.POST.get(category)

                try:
                    cat_score = CandidateEvaluationScore.objects.get(evaluation=candidate_evaluation, category=category)
                    cat_score.score = score

                except CandidateEvaluationScore.DoesNotExist:
                    cat_score = CandidateEvaluationScore.objects.create(evaluation=candidate_evaluation,
                                                                        topic="teamwork",
                                                                        category=category,
                                                                        score=score)
                cat_score.save()

        candidate_evaluation.date = timezone.now()
        candidate_evaluation.user = request.user
        candidate_evaluation.save()

    registered_scores = {}
    for item in candidate_evaluation.scores.all():
        score_item = {item.category: item.score}
        registered_scores.update(score_item)

    return render(request, template_name='recruiter/partials/evaluation_panel.html', context={"candidate_evaluation": candidate_evaluation, "candidate_evaluation_comments": candidate_evaluation.comment, "scores": registered_scores, "candidate": candidate, "job_posting": job_posting, "eval_categories": eval_categories})


@login_required()
def register_one_to_one(request, jp_id, pk):

    candidate = Candidate.objects.get(pk=pk)
    job_posting = JobPosting.objects.get(jp_id=jp_id)

    try:
        candidate_evaluation = CandidateEvaluation.objects.get(candidate=candidate, job_posting=job_posting)

    except CandidateEvaluation.DoesNotExist:
        candidate_evaluation = CandidateEvaluation.objects.create(candidate=candidate, job_posting=job_posting,
                                                                  tenant=job_posting.tenant)

        candidate_evaluation.date = timezone.now()
        candidate_evaluation.user = request.user
        candidate_evaluation.save()

    if request.method == "POST":
        note = request.POST.get("notes_one_to_one")
        note_item = CandidateInterviewNotes.objects.create(evaluation=candidate_evaluation, note=note, user=request.user, date=timezone.now())
        note_item.save()

    notes = CandidateInterviewNotes.objects.filter(evaluation = candidate_evaluation)

    return render(request, 'recruiter/partials/evaluation_one_to_one_panel.html', {'candidate': candidate, 'job_posting': job_posting, 'notes': notes})


@login_required()
def group_interview_debrief(request, jp_id):

    if request.method == "GET":
        job_posting = JobPosting.objects.get(jp_id=jp_id)
        jp_flow_control = JobPostingFlow(job_posting)

        acceptable_statuses = ACCEPTABLE_CANDIDATE_STATUSES.get(jp_flow_control._get_status(), [])
        print(acceptable_statuses)
        candidates = Candidate.objects.filter(recruiter_status__in=acceptable_statuses)

        return render(request=request, template_name="recruiter/group_interview_debrief.html",
                      context={"job_posting": job_posting, "candidates": candidates})


@login_required
def job_posting_delete(request, jp_id):

    job_posting = get_object_or_404(JobPosting, jp_id=jp_id)

    if True:

        for candidate in Candidate.objects.filter(recruiter_posting=job_posting.pk, job_posting=job_posting):

            candidate.recruiter_posting = 0
            candidate.job_posting = None

            candidate.recruiter_status = CandidateStatus.AVAILABLE
            #    print(candidate.contact.fullname)
            candidate.save()

        CandidateList.objects.filter(posting_id=job_posting.id).delete()
        job_posting.delete()

        return redirect(reverse("recruiter:dashboard"))

    else:
        return redirect(reverse("recruiter:job_posting_details"), args=[jp_id])


@login_required
def job_posting_update(request, pk):
    # Logic to update the record based on the form data
    # You might want to use a Django form or model form here for validation and security
    job_posting = JobPosting.objects.get(pk=pk)
    form = JobPostingForm(request.POST, request.FILES, instance=job_posting)
    original_description = job_posting.description
    original_vacancies = job_posting.vacantes

    if form.is_valid():

        # Change requires to run the match again, cleaning the match.
        for candidate in Candidate.objects.filter(recruiter_posting=job_posting.id, job_posting=job_posting):

            candidate.recruiter_posting = 0
            candidate.job_posting = None

            candidate.recruiter_status = "A"
            candidate.save()

        CandidateList.objects.filter(posting_id=job_posting.id).delete()

        retries = 5
        delay = 3
        for attempt in range(retries):
            try:
                job = candidate_matching.apply_async(args=[job_posting.tenant.id, job_posting.id], queue=settings.MEDIUM_PRIORITY_Q)
                print(f'queued job: {job.id}')
                break
            except OperationalError as e:
                print(e)
                if attempt < retries - 1:
                    time.sleep(delay)  # Wait before retrying
                else:
                    raise

        form.save()

        return redirect(reverse("recruiter:dashboard"))

    else:
        # Handle form errors
        pass


@login_required
def message_templates_configuration(request, jp_id):

    job_posting = JobPosting.objects.get(jp_id=jp_id)
    if request.method == "POST":

        job_posting.psicotest_template = request.POST.get("psicotest_template")
        job_posting.invitation_template = request.POST.get("invitation_template")
        job_posting.reminder_template = request.POST.get("reminder_template")

        job_posting.save()

        return HttpResponse(status=204, headers={
            'HX-Trigger': json.dumps({
                "showMessage": f"Mensajes configurados!",
                "refresh_data": None,
            })
        })

    else:
        psicotest_template = job_posting.psicotest_template
        invitation_template = job_posting.invitation_template
        reminder_template = job_posting.invitation_template

        template_config_form = JobPostingMessageTemplates(initial={'psicotest_template': psicotest_template,
                                                                   'invitation_template': invitation_template,
                                                                   'reminder_template': reminder_template})

        return render(request, template_name='recruiter/partials/job_posting_message_templates_form.html', context={'job_posting': job_posting, 'template_config_form': template_config_form})


@login_required
def update_recruiter_dashboard_kpis(request):
    tenant = current_tenant.get()

    postings = JobPosting.objects.exclude(status=JobPostingStatus.CLOSED).filter(tenant=tenant).count()
    candidates = Candidate.objects.filter(tenant=tenant)
    available_candidates = candidates.filter(recruiter_status__exact="A").count()
    in_proces_candidates = candidates.exclude(recruiter_posting=0, job_posting__isnull=True, recruiter_status__in=["X", "H", "S", "A"]).count()
    hired_candidates = candidates.filter(recruiter_status__exact="H").count()
    stand_by_candidates = candidates.filter(recruiter_status__exact="S").count()
    candidates_with_psigma = candidates.filter(psicotest_score__isnull=False).count()
    candidates_geocoded = candidates.filter(latitude__isnull=False, longitude__isnull=False).count()
    candidates_summarized = candidates.exclude(recruiter_summary__exact="").all().count()

    kpis = [
            {"name": "Llamados", "value": postings},
            {"name": "Disponibles", "value": available_candidates},
            {"name": "En Proceso", "value": in_proces_candidates},
            {"name": "Contratados", "value": hired_candidates},
            {"name": "Seleccionados", "value": stand_by_candidates},
            {"name": "Prueba Ser", "value": candidates_with_psigma},
                #  {"name": "candidates_geocoded", "value": candidates_geocoded},
                #  {"name": "", "value": candidates_summarized}
            ]


    context = {
        "kpis": kpis,
    }

    return render(request, 'recruiter/partials/dashboard_kpis.html', context=context)

@login_required
def candidate_clusters(request):
    tenant = current_tenant.get()
    points = plot_clusters(tenant=tenant)

    context = {
        "points": points.to_html()
    }

    return render(request, 'recruiter/partials/cluster_plots.html', context=context)

def candidate_debug(request):
    candidate_list = Candidate.objects.all()
    jobs = JobPosting.objects.all()

    for job in jobs:
        if job.image and job.image.file:
            print(job.image, job.image.url)

    for candi in candidate_list:
        print(f"Pic for {candi.contact.fullname}")
        print(candi.profile_picture.name)
        try:

            print(candi.profile_picture)
        except Exception as e:
            print(f'{candi.contact.fullname} Error: {e}')

        try:
            print(candi.profile_picture.url)
        except Exception as e:
            print(f'{candi.contact.fullname} Error: {e}')

    return render(request, template_name="main.html", context={"candidates": candidate_list})


@login_required
def recruiter(request):
    menu = AppMenu.objects.filter(app="recruiter")

    context = {
        "menu": menu,
        "menu_title": "Recruiter",
        "menu_icon": "mdi mdi-human",
        "default_screen": "convocatoria/dashboard/update_kpis"
    }

    return render(request, "moio_main.html", context=context)


@login_required
def candidate_add(request):
    tenant = current_tenant.get()
    if request.method == "POST":
        if request.POST.get("step") == "1":
            cedula = request.POST.get("cedula")
            try:
                candidate = Candidate.objects.get(document_id=cedula)
                context = {
                    "step": 2,
                    "cedula": cedula,
                    "candidate": candidate,
                    "content_page": "recruiter/candidate_add_form.html",
                    "page_title": "Actualizar Candidato",

                }
            except Candidate.DoesNotExist:
                context = {
                    "step": 2,
                    "cedula": cedula,
                    "candidate": None,
                    "content_page": "recruiter/candidate_add_form.html",
                    "page_title": "Actualizar Candidato"

                }
            return render(request, template_name="recruiter/candidate_add_form.html", context=context)


        elif request.POST.get("step") == "2":

            action = request.POST.get("action")
            cedula = str(request.POST.get("candidate_cedula")).strip()

            contact = Contact.create_or_update(
                phone=request.POST.get("candidate_phone"),
                tenant=tenant,
                fullname=request.POST.get("candidate_name"),
                email=request.POST.get("candidate_email"),
                source="recruiter",
                role="candidate"
                )

            if action == "create":
                candidate = Candidate.objects.create(contact=contact,
                                                     document_id=cedula,
                                                     date_birth=request.POST.get("candidate_birthdate"),
                                                     city=request.POST.get("candidate_city"),
                                                     state=request.POST.get("candidate_state"),
                                                     postal_code=request.POST.get("candidate_postal_code"),
                                                     address=request.POST.get("candidate_address"),
                                                     self_summary=request.POST.get("candidate_self_summary"),
                                                     work_experience=request.POST.get("candidate_work_experience"),
                                                     education=request.POST.get("candidate_education"),
                                                     tenant=tenant,
                                                     )
                candidate.save()

            else:

                candidate = Candidate.objects.get(document_id=cedula)
                candidate.contact = contact
                candidate.date_birth = request.POST.get("candidate_birthdate")
                candidate.city = request.POST.get("candidate_city")
                candidate.state = request.POST.get("candidate_state")
                candidate.postal_code = request.POST.get("candidate_postal_code")
                candidate.address = request.POST.get("candidate_address")
                candidate.tenant = tenant
                candidate.self_summary = request.POST.get("candidate_self_summary")
                candidate.work_experience = request.POST.get("candidate_work_experience")
                candidate.education = request.POST.get("candidate_education"
                                                       )
                candidate.save()

            if request.FILES.get("profile_pic_input"):
                profile_pic = request.FILES.get("profile_pic_input")
                candidate.profile_picture = profile_pic
                candidate.save()

            return HttpResponse(
                status=204,
                headers={
                    'HX-Trigger': json.dumps({
                        "showMessage": f'Candidato {cedula} - {action}d'
                    })
                })

    else:
        context = {
            "step": 1,
            "content_page": "recruiter/candidate_add_form.html",
            "modal_size": "s",
            "page_title": "Agregar Candidato"
        }

        #return render(request, template_name="recruiter/candidate_add_form.html", context=context)
        return render(request, template_name="partials/modal_factory.html", context=context)
