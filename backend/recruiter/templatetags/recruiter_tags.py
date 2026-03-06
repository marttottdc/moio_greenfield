from string import Template
from urllib.parse import quote
from django.utils.html import escape
from django import template

from recruiter.models import JobPosting

register = template.Library()


@register.filter(name='get_value')
def get_value(dictionary, key):
    return dictionary.get(key)


@register.filter(name='template_replace')
def template_replace(template_string, object1):
    # Define el mapeo entre placeholders y nombres reales de variables

    job_posting = JobPosting.objects.get(pk=object1.recruiter_posting)

    placeholder_to_variable = {

        'nombre_candidato': 'contact.fullname',
        'psigma_url': 'psigma_link',
        'fecha_prueba_grupal': 'group_interview_date',
        'descripcion_llamado': 'description',

      # Añade más mapeos según sea necesario
    }

    # Prepare the formatted template
    formatted_template = template_string.replace("{{", "$").replace("}}", "")
    template = Template(formatted_template)

    # Map the values using the placeholder_to_variable dictionary
    mapped_values = {}
    for placeholder, variable in placeholder_to_variable.items():
        # Use Django's template variable resolution
        try:
            value = eval(f'object1.{variable}')

        except Exception as e:
            try:
                value = getattr(job_posting, variable)

            except Exception as e:
                value = ""


        mapped_values[placeholder] = escape(value)  # Use escape to prevent HTML injection

    return template.safe_substitute(mapped_values)