
from crm.models import Contact

from django.db import transaction
from django.db.models import Q

from campaigns.models import Audience, AudienceKind, Campaign
from campaigns.forms import ConditionForm, AudienceBasicForm
from campaigns.core.service import compile_rules
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.forms import modelform_factory
from campaigns.models import Audience
from campaigns.forms import ConditionFormSet  # your existing formset
from central_hub.context_utils import current_tenant


@login_required
def audience_form(request, pk=None):
    """Handle audience create/edit"""
    tenant = current_tenant.get()

    # Get existing audience or create new
    audience = None
    if pk:
        audience = get_object_or_404(Audience, pk=pk, tenant=tenant)

    # Initialize formset
    if audience and audience.rules:
        initial_data = [{
            "field": k,
            "value": v
        } for cond in audience.rules.get("and", []) for k, v in cond.items()]
    else:
        initial_data = []

    if request.method == 'POST':
        formset = ConditionFormSet(request.POST)
        name = request.POST.get("name", "").strip()

        errors = []
        if not name:
            errors.append("Audience name is required")

        if not formset.is_valid():
            errors.append("Please fix the form errors")

        if not errors:
            try:
                # Build rules
                rules = {
                    "and": [{
                        f.cleaned_data["field"]: f.cleaned_data["value"]
                    } for f in formset
                     if f.cleaned_data and not f.cleaned_data.get("DELETE", False)]
                }

                # Save audience
                with transaction.atomic():
                    if audience:
                        audience.name = name
                        audience.rules = rules if rules["and"] else None
                        audience.save()
                    else:
                        audience = Audience.objects.create(
                            tenant=tenant,
                            name=name,
                            kind=AudienceKind.DYNAMIC if rules["and"] else AudienceKind.STATIC,
                            rules=rules if rules["and"] else None
                        )

                    # Update audience size for dynamic audiences
                    if audience.kind == AudienceKind.DYNAMIC and audience.rules:
                        from campaigns.core.service import build_dynamic_audience
                        build_dynamic_audience(audience)

                # Return updated audience list
                audiences = Audience.objects.filter(tenant=tenant)
                context = {
                    'audiences': audiences
                }
                return render(request, 'campaigns/partials/audience_list.html',context)

            except Exception as e:
                errors.append(f"Error saving audience: {str(e)}")

        # If there are errors, re-render the form with errors
        if errors:
            context = {
                "aud": audience,
                "formset": formset,
                "errors": errors
            }
            return render(request, "campaigns/modals/audience_form_modal.html", context)

    else:
        formset = ConditionFormSet(initial=initial_data)

    context = {
        "aud": audience,
        "formset": formset
    }

    return render(request, "campaigns/modals/audience_form_modal.html", context)


@login_required
def audience_new(request):
    """Create new audience"""
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        kind = request.POST.get("kind", "static")

        if not name:
            return render(request, "campaigns/modals/audience_form_modal.html", {
                "errors": ["Audience name is required"]
            })

        tenant = current_tenant.get()
        errors = []

        if kind == "dynamic":
            # Handle dynamic audience with rules
            formset = ConditionFormSet(request.POST)
            if formset.is_valid():
                # Build rules from formset
                rules = {
                    "and": [{
                        f.cleaned_data["field"]: f.cleaned_data["value"]
                    } for f in formset
                            if f.cleaned_data and not f.cleaned_data.get("DELETE", False)]
                }

                # Create the audience
                audience = Audience.objects.create(
                    tenant=tenant,
                    name=name,
                    description=description,
                    kind="DYNAMIC",
                    rules=rules if rules["and"] else None
                )

                # Build the audience if it has rules
                if rules["and"]:
                    try:
                        from campaigns.core.service import build_dynamic_audience
                        build_dynamic_audience(audience)
                    except Exception as e:
                        errors.append(f"Error building audience: {str(e)}")
            else:
                errors.append("Invalid conditions")
        else:
            # Handle static audience
            audience = Audience.objects.create(
                tenant=tenant,
                name=name,
                description=description,
                kind="STATIC",
                size=0
            )

        if not errors:
            return render(request, "campaigns/partials/audience_list.html", {
                "audiences": Audience.objects.filter(tenant=tenant)
            })

        # If there are errors, re-render the form with errors
        context = {
            "errors": errors
        }
        if kind == "dynamic":
            context["formset"] = formset
        return render(request, "campaigns/modals/audience_form_modal.html", context)

    else:
        formset = ConditionFormSet()

    context = {
        "formset": formset
    }

    return render(request, "campaigns/modals/audience_form_modal.html", context)