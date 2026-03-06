
"""

return HttpResponse(
    status=204,
    headers={
        "HX-Trigger": json.dumps({
            "closeModal": None,           # <-- add this
            "showMessage": "Mensajes configurados!",
            "refresh_data": None,
        })
    },
)

"""

# hx-post="{% url 'crm:import_data' %}"
# hx-headers='{"X-CSRFToken":"{{ csrf_token }}"}'
# hx-vals='{"import_item":"{{ import_item.modal_id }}"}'

"""
<select name="whatsapp_template" id="id_whatsapp_template" class="form-select">
        <option value="">--- Select Template ---</option>
        {% for template in templates %}
        <option value="{{ template.id }}" 
                data-category="{{ template.category }}"
                data-components="{{ template.components|length }}">
            {{ template.name }} ({{ template.category }})
        </option>
        {% endfor %}
    </select>
"""