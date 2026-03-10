import json

from celery.utils.time import timezone
from django.template.loader import render_to_string

from campaigns.core.service import _normalize_rows
from crm.models import Contact

from django.db import transaction
from django.db.models import Q

from campaigns.models import Audience, AudienceKind, Campaign
from campaigns.forms import ConditionForm, AudienceBasicForm
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseBadRequest
from django.forms import modelform_factory
from campaigns.models import Audience
from campaigns.forms import ConditionFormSet  # your existing formset
from central_hub.context_utils import current_tenant
from campaigns.core.audience_filters import compute_audience_preview, compute_audience, FIELD_MAP
from central_hub.models import TenantConfiguration


BasicAudienceForm = modelform_factory(
    Audience,
    fields=("name", "description", "kind"),
)


@login_required
def search_contacts(request):
    """Search contacts for static audience selection"""
    tenant = current_tenant.get()
    query = request.POST.get('search', '').strip()

    if len(query) < 2:
        return render(request, 'campaigns/partials/contact_search_results.html', {
            'contacts': [],
            'query': query
        })

    from crm.models import Contact
    contacts = Contact.objects.filter(
        tenant=tenant
    ).filter(
        Q(fullname__icontains=query) |
        Q(email__icontains=query) |
        Q(phone__icontains=query)
    )[:20]

    context = {
        'contacts': contacts,
        'query': query
    }
    return render(request, 'campaigns/partials/contact_search_results.html', context)


@login_required
def toggle_contact(request):
    """Add or remove contact from static audience"""
    if request.method != 'POST':
        return HttpResponse(status=405)

    tenant = current_tenant.get()
    contact_id = request.POST.get('contact_id')
    audience_id = request.POST.get('audience_id')
    action = request.POST.get('action')  # 'add' or 'remove'

    if not all([contact_id, audience_id, action]):
        return HttpResponse("Missing parameters", status=400)

    try:
        from crm.models import Contact
        audience = get_object_or_404(Audience, pk=audience_id, tenant=tenant)
        contact = get_object_or_404(Contact, pk=contact_id, tenant=tenant)

        if action == 'add':
            from campaigns.core.service import add_static_contacts
            add_static_contacts(audience, [contact])
        elif action == 'remove':
            from campaigns.core.service import remove_static_contacts
            remove_static_contacts(audience, [contact])

        return HttpResponse("OK")
    except Exception as e:
        return HttpResponse(f"Error: {str(e)}", status=500)


@login_required
def audience_contacts(request, audience_id):
    """Load audience contacts for display"""
    tenant = current_tenant.get()
    audience = get_object_or_404(Audience, pk=audience_id, tenant=tenant)

    # Get contacts through membership
    from campaigns.models import AudienceMembership
    memberships = AudienceMembership.objects.filter(
        audience=audience
    ).select_related('contact')[:50]  # Limit for performance

    context = {
        'audience': audience,
        'memberships': memberships
    }
    return render(request, 'campaigns/partials/audience_contacts_list.html', context)


@login_required
def audience_list(request):
    print("Listing audiences")
    tenant = current_tenant.get()

    all_audiences = Audience.objects.filter(tenant=tenant)

    context = {
        "audiences": all_audiences
    }

    return render(request, 'campaigns/partials/audience_list.html', context)


@login_required
def condition_row(request):
    prefix = request.GET.get("prefix", "form")
    total = int(request.GET.get(f"{prefix}-TOTAL_FORMS", 0))

    row_html = render_to_string(
        "campaigns/partials/_condition_row.html",
        {"form": ConditionForm(prefix=f"{prefix}-{total}")},
        request=request,
    )
    # bump only this formset's TOTAL_FORMS
    oob_html = f'''
      <input type="hidden" name="{prefix}-TOTAL_FORMS"
             value="{total + 1}" id="id_{prefix}-TOTAL_FORMS"
             hx-swap-oob="true">
    '''
    return HttpResponse(row_html + oob_html)


@login_required
def condition_delete(request):
    tenant = current_tenant.get()
    row_prefix = request.POST.get("row_prefix")
    aud_id = request.POST.get("aud_id")
    if not row_prefix or not aud_id:
        return HttpResponseBadRequest("row_prefix and aud_id required")

    aud = get_object_or_404(Audience, pk=aud_id, tenant=tenant)

    # Copy POST and force-check the DELETE for that row
    data = request.POST.copy()
    data[f"{row_prefix}-DELETE"] = "on"

    # Bind both formsets using the mutated data
    and_fs = ConditionFormSet(data=data, prefix="and-conditions")
    or_fs = ConditionFormSet(data=data, prefix="or-conditions")

    # Default response: swap the row to a hidden, checked DELETE stub
    # NOTE: ConditionForm by itself has no DELETE field; render the input manually.
    stub = f'''
    <div id="{row_prefix}-row" class="d-none">
      <input type="checkbox" name="{row_prefix}-DELETE" id="id_{row_prefix}-DELETE" checked>
    </div>
    '''

    # If valid, persist rules & members + OOB preview update
    if and_fs.is_valid() and or_fs.is_valid():
        and_rules = [cd for cd in and_fs.cleaned_data if cd and not cd.get("DELETE")]
        or_rules = [cd for cd in or_fs.cleaned_data  if cd and not cd.get("DELETE")]
        base_qs = Contact.objects.filter(tenant=tenant)

        with transaction.atomic():
            aud.rules = {"and": and_rules, "or": or_rules}
            aud.is_draft = True  # stays draft until explicit Save
            aud.save(update_fields=["rules", "is_draft"])

            matched = compute_audience(
                and_rules, or_rules, base_qs,
                audience=aud, m2m_attr="contacts", replace=True,
                m2m_through_defaults={"tenant": tenant},
            )
        count = matched.count()

        # Send preview count as an out-of-band swap, so no extra request is needed
        oob = f'<span id="preview-count" hx-swap-oob="true">{count}</span>'
        return HttpResponse(stub + oob)

    # Invalid: still remove visually, but don’t change DB; preview remains as-is
    return HttpResponse(stub)


def preview_count(request):
    tenant = current_tenant.get()
    and_set = ConditionFormSet(request.POST or None, prefix="and-conditions")
    or_set  = ConditionFormSet(request.POST or None,  prefix="or-conditions")

    if and_set.is_valid() and or_set.is_valid():
        and_rules = [cd for cd in and_set.cleaned_data if cd and not cd.get("DELETE")]
        or_rules = [cd for cd in or_set.cleaned_data  if cd and not cd.get("DELETE")]
        base_qs = Contact.objects.filter(tenant=tenant)
        count = compute_audience_preview(and_rules, or_rules, base_qs)
        return HttpResponse(str(count))
    return HttpResponse("—")


@login_required
def audience_create_basics(request):
    if request.method != "POST":
        form = AudienceBasicForm()
        context = {
            "form": form
        }
        return render(request, "campaigns/modals/audience_form.html", context)

    form = AudienceBasicForm(request.POST)
    if not form.is_valid():
        context = {

            "form": form,
            "errors": form.errors
        }

        return render(request, "campaigns/modals/audience_form.html", context)

    tenant = current_tenant.get()
    aud = form.save(commit=False)
    aud.tenant = tenant
    aud.is_draft = True
    aud.save()

    if aud.kind == AudienceKind.DYNAMIC:
        formset = ConditionFormSet()
        #return render(request, "campaigns/modals/audience_config_dynamic.html", {"aud": aud, "formset": formset})
        # in step 1 flow
        return render(request, "campaigns/modals/audience_config_dynamic_assisted.html", {"aud": aud})

    else:
        contacts = Contact.objects.filter(tenant=tenant)
        return render(request, "campaigns/modals/audience_config_static.html", {"aud": aud, "contacts": contacts})


@login_required
def audience_configure(request, pk):
    tenant = current_tenant.get()
    aud = get_object_or_404(Audience, pk=pk, tenant=tenant)

    if aud.kind != AudienceKind.DYNAMIC:
        return render(request, "campaigns/modals/audience_config_static.html", {"aud": aud})

    if request.method == "POST":
        # Re-render with posted (invalid) data
        and_set = ConditionFormSet(request.POST, prefix="and-conditions")
        or_set = ConditionFormSet(request.POST,  prefix="or-conditions")
    else:
        # First load / reopen -> populate from persisted rules
        data = aud.rules or {}
        and_initial = _normalize_rows(data.get("and"))
        or_initial = _normalize_rows(data.get("or"))
        and_set = ConditionFormSet(prefix="and-conditions", initial=and_initial)
        or_set = ConditionFormSet(prefix="or-conditions",  initial=or_initial)

    context = {
        "aud": aud,
        "formset_and": and_set,
        "formset_or": or_set,
    }
    # return render(request,template_name="campaigns/modals/audience_config_dynamic.html", context=context)

    return render(request, "campaigns/modals/audience_config_dynamic_assisted.html", context)


@login_required
def audience_assisted_preview(request, pk):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    tenant = current_tenant.get()
    aud = get_object_or_404(Audience, pk=pk, tenant=tenant)

    prompt = (request.POST.get("prompt") or "").strip()
    if not prompt:
        html = '<div class="text-muted small">Write a prompt to preview.</div>'
        # reset preview count
        oob = '<span id="preview-count" hx-swap-oob="true">—</span>'
        return HttpResponse(html + oob)

    # build rule tree
    try:
        config = TenantConfiguration.objects.get(tenant=tenant)
        tree = generate_rules_tree(
            config,
            prompt,
            allowed_fields=ASSISTED_ALLOWED_FIELDS,
            allowed_ops=sorted(list(ALLOWED_OPS)),
            field_synonyms={k.lower(): v for k, v in ASSISTED_FIELD_SYN.items()},
            op_synonyms={k.lower(): v for k, v in ASSISTED_OP_SYN.items()},
            default_case_ci=True
        )
    except Exception as e:

        html = f'<div class="alert alert-warning mb-2">Failed to parse prompt: {e}</div>'
        oob = '<span id="preview-count" hx-swap-oob="true">—</span>'
        return HttpResponse(html + oob)

    # compute preview count
    base_qs = Contact.objects.filter(tenant=tenant)
    q = tree_to_q(Contact, tree, allowed_fields=ASSISTED_ALLOWED_FIELDS, default_ci=True)
    try:
        count = base_qs.filter(q).count()
    except Exception:
        count = 0

    # persist tree + prompt on the Audience
    with transaction.atomic():
        try:
            aud.rules = {"tree": tree.model_dump(mode="json"), "prompt": prompt}
        except Exception:
            aud.rules = {"tree": tree.dict(), "prompt": prompt}
        aud.is_draft = True
        aud.save(update_fields=["rules", "is_draft"])

    # render a simple nested-list summary of the rules
    def _render_tree_html(node: RuleNode) -> str:
        html_parts = ["<ul>"]
        def walk(n):

            if isinstance(n, Rule):
                field, op = n.field, n.op
                val, val_to = n.value, getattr(n, "value_to", None)
                if op == "between":
                    html_parts.append(f"<li>{field} {op} {val} and {val_to}</li>")
                elif op == "in":
                    items = ", ".join([str(x) for x in (val or [])])
                    html_parts.append(f"<li>{field} {op} {items}</li>")
                elif op == "isnull":
                    cond = 'is null' if (val if val is not None else True) else 'is not null'
                    html_parts.append(f"<li>{field} {cond}</li>")
                elif op == "istrue":
                    html_parts.append(f"<li>{field} is true</li>")
                elif op == "isfalse":
                    html_parts.append(f"<li>{field} is false</li>")
                else:
                    html_parts.append(f"<li>{field} {op} {val}</li>")
            else:
                logic = getattr(n, "logic", "and").upper()
                html_parts.append(f"<li>{logic}<ul>")
                for child in getattr(n, "children", []):
                    walk(child)
                html_parts.append("</ul></li>")
        walk(node)
        html_parts.append("</ul>")
        return "".join(html_parts)

    rules_html = _render_tree_html(tree)
    oob = f'<span id="preview-count" hx-swap-oob="true">{count}</span>'
    return HttpResponse(rules_html + oob)


@login_required
def audience_assisted_save(request, pk):
    """Finalize: activate, rebuild membership, store size; tenant-scoped."""
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    tenant = current_tenant.get()
    aud = get_object_or_404(Audience, pk=pk, tenant=tenant)

    prompt = (request.POST.get("prompt") or "").strip()

    # try to reuse stored tree if no new prompt
    stored_tree_json = None
    if isinstance(aud.rules, dict):
        stored_tree_json = aud.rules.get("tree")

    tree = None
    # build tree from prompt or parse stored tree
    if prompt:
        client = OpenAI(api_key=tenant.openai_api_key)
        tree = generate_rules_tree(
            client,
            prompt,
            allowed_fields=ASSISTED_ALLOWED_FIELDS,
            allowed_ops=sorted(list(ALLOWED_OPS)),
            field_synonyms={k.lower(): v for k, v in ASSISTED_FIELD_SYN.items()},
            op_synonyms={k.lower(): v for k, v in ASSISTED_OP_SYN.items()},
            default_case_ci=True,
            openai_model="gpt-4.1-mini",
        )
    elif stored_tree_json:
        from audience_ai_min.rules import RuleNode as _RuleNode
        tree = _RuleNode.model_validate(stored_tree_json)

    # compile Q
    if tree is not None:
        q = tree_to_q(Contact, tree, allowed_fields=ASSISTED_ALLOWED_FIELDS, default_ci=True)
    else:
        from django.db.models import Q as _Q
        q = _Q()

    base_qs = Contact.objects.filter(tenant=tenant)
    try:
        matched_qs = base_qs.filter(q)
    except Exception:
        matched_qs = base_qs.none()
    matched_ids = list(matched_qs.values_list("pk", flat=True))

    # persist final rules and membership
    with transaction.atomic():
        if tree is not None:
            try:
                aud.rules = {"tree": tree.model_dump(mode="json"), "prompt": prompt or aud.rules.get("prompt")}
            except Exception:
                aud.rules = {"tree": tree.dict(), "prompt": prompt or (aud.rules.get("prompt") if isinstance(aud.rules, dict) else "")}
        else:
            aud.rules = {"prompt": prompt or (aud.rules.get("prompt") if isinstance(aud.rules, dict) else "")}

        aud.is_draft = False
        if hasattr(aud, "is_active"):
            aud.is_active = True
        if hasattr(aud, "activated_at"):
            aud.activated_at = timezone.now()
        aud.save(update_fields=[f for f in ["rules", "is_draft", "is_active", "activated_at"] if hasattr(aud, f) or f in ("rules", "is_draft")])

        # rebuild membership
        if hasattr(aud, "contacts"):
            rel = getattr(aud, "contacts")
            rel.set(matched_ids, through_defaults={"tenant": tenant})
        count = len(matched_ids)

        # update size/members_count fields if they exist
        changed = []
        if hasattr(aud, "size"):
            aud.size = count
            changed.append("size")
        if hasattr(aud, "members_count"):
            aud.members_count = count
            changed.append("members_count")
        if changed:
            aud.save(update_fields=changed)

    # refresh the audience list
    audiences = Audience.objects.filter(tenant=tenant).order_by("-id")
    resp = render(request, "campaigns/partials/audience_list.html", {"audiences": audiences})
    resp["HX-Trigger"] = json.dumps({"closeModal": True, "showMessage": f"Audience activated — {count} members"})
    return resp


@login_required
def audience_dynamic_save(request, pk):
    tenant = current_tenant.get()
    aud = get_object_or_404(Audience, pk=pk, tenant=tenant)

    if request.method != "POST":
        return audience_configure(request, pk)

    # Bind BOTH formsets from the POST (final validation)
    and_set = ConditionFormSet(request.POST, prefix="and-conditions")
    or_set  = ConditionFormSet(request.POST,  prefix="or-conditions")

    if not (and_set.is_valid() and or_set.is_valid()):
        return render(
            request,
            "campaigns/modals/audience_config_dynamic.html",
            {
                "aud": aud,
                "formset_and": and_set,
                "formset_or": or_set,
                "errors": ["Invalid conditions. Fix highlighted rows."],
            },
        )

    # Extract non-deleted rows
    and_rules = [cd for cd in and_set.cleaned_data if cd and not cd.get("DELETE")]
    or_rules  = [cd for cd in or_set.cleaned_data  if cd and not cd.get("DELETE")]

    if not and_rules and not or_rules:
        return render(
            request,
            "campaigns/modals/audience_config_dynamic.html",
            {
                "aud": aud,
                "formset_and": and_set,
                "formset_or": or_set,
                "errors": ["Add at least one condition."],
            },
        )

    base_qs = Contact.objects.filter(tenant=tenant)

    with transaction.atomic():
        # 1) Persist final rules and flip draft -> false; activate if field exists
        aud.rules = {"and": and_rules, "or": or_rules}
        aud.is_draft = False

        update_fields = ["rules", "is_draft"]

        if hasattr(aud, "is_active"):
            aud.is_active = True
            update_fields.append("is_active")
        if hasattr(aud, "activated_at"):
            from django.utils import timezone
            aud.activated_at = timezone.now()
            update_fields.append("activated_at")

        aud.save(update_fields=update_fields)

        # 2) Rebuild membership (tenant-scoped; NOT NULL tenant on through)
        matched_qs = compute_audience(
            and_rules,
            or_rules,
            base_qs,
            audience=aud,
            m2m_attr="contacts",                 # adjust if your M2M accessor differs
            replace=True,
            m2m_through_defaults={"tenant": tenant},
        )

        # 3) Store size/members count if the model has such a field
        count = matched_qs.count()
        count_fields = []
        if hasattr(aud, "size"):
            aud.size = count
            count_fields.append("size")
        if hasattr(aud, "members_count"):
            aud.members_count = count
            count_fields.append("members_count")
        if count_fields:
            aud.save(update_fields=count_fields)

    # Refresh list for this tenant
    audiences = Audience.objects.filter(tenant=tenant).order_by("-id")
    resp = render(request, "campaigns/partials/audience_list.html", {"audiences": audiences})
    resp["HX-Trigger"] = json.dumps(
        {"closeModal": True, "showMessage": f"Audience activated — {count} members"}
    )
    return resp


@login_required
def audience_autosave(request, pk):
    """
    On any change:
      - If both formsets are valid: persist rules AND upsert M2M members (tenant-scoped),
        keep is_draft=True, and return the preview count.
      - If invalid: do NOT change DB; return "—".
    """
    tenant = current_tenant.get()
    aud = get_object_or_404(Audience, pk=pk, tenant=tenant)

    and_set = ConditionFormSet(request.POST or None, prefix="and-conditions")
    or_set  = ConditionFormSet(request.POST or None,  prefix="or-conditions")

    if not (and_set.is_valid() and or_set.is_valid()):
        return HttpResponse("—")

    and_rules = [cd for cd in and_set.cleaned_data if cd and not cd.get("DELETE")]
    or_rules  = [cd for cd in or_set.cleaned_data  if cd and not cd.get("DELETE")]

    base_qs = Contact.objects.filter(tenant=tenant)

    with transaction.atomic():
        # 1) persist rules, keep draft flag
        aud.rules = {"and": and_rules, "or": or_rules}
        aud.is_draft = True
        aud.save(update_fields=["rules", "is_draft"])

        # 2) upsert members in the through table (tenant-scoped)
        matched_qs = compute_audience(
            and_rules,
            or_rules,
            base_qs,
            audience=aud,
            m2m_attr="contacts",                 # adjust if needed
            replace=True,
            m2m_through_defaults={"tenant": tenant},
        )

    # 3) return preview count
    return HttpResponse(str(matched_qs.count()))


@login_required
def audience_static_finalize(request, pk):
    """
    Finalize static audience. Membership is toggled via your existing /toggle-contact
    endpoint. Here we just compute size, mark non-draft, and close modal.
    """
    aud = get_object_or_404(Audience, pk=pk, tenant=current_tenant.get())

    # Recompute size using your M2M table
    aud.size = aud.membership.count()  # adjust to your relation name
    aud.is_draft = False
    aud.save(update_fields=["size", "is_draft"])

    audiences = Audience.objects.filter(tenant=current_tenant.get()).order_by("-id")
    resp = render(request, "campaigns/partials/audience_list.html", {"audiences": audiences})
    resp["HX-Trigger"] = '{"closeModal": true, "showMessage": "Audience saved"}'
    return resp


@login_required
def audience_delete(request, pk):
    aud = get_object_or_404(Audience, pk=pk, tenant=current_tenant.get())
    if aud.is_draft:
        aud.delete()
        message = '{"closeModal": true, "showMessage": "Audience deleted"}'
    else:
        message = '{"closeModal": true, "showMessage": "Cannot delete active audience"}'

    audiences = Audience.objects.filter(tenant=current_tenant.get()).order_by("-id")
    resp = render(request, "campaigns/partials/audience_list.html", {"audiences": audiences})
    resp["HX-Trigger"] = message
    return resp
