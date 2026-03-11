import datetime

from crm.models import Branch, Contact, Company
from crm.lib.dac_api import DacApi
from central_hub.tenant_config import get_tenant_config_by_id
import phonenumbers
from django.core.exceptions import ValidationError
from phonenumbers import geocoder, PhoneNumberFormat, parse, format_number
from phonenumbers.phonenumberutil import number_type
from phonenumbers.phonenumberutil import region_code_for_number
from phonenumbers.phonenumberutil import is_possible_number, is_valid_number



def import_branches(df, tenant):

    for index, row in df.iterrows():

        print(row["tipo_sucursal"], row["nombre_local"], row["direccion"], row["nombre_gerente"], row["telefono_gerente"])

        company = Company.objects.get(tenant=tenant)

        try:
            branch = Branch.objects.get(name__exact=row["nombre_local"], tenant=tenant)
            branch.address = row["direccion"]
            branch.state = row["departamento"]
            branch.type = row["tipo_sucursal"]
            branch.save()


        except Branch.DoesNotExist:

            branch = Branch(
                name=row["nombre_local"],
                address=row["direccion"],
                state=row["departamento"],
                tenant=tenant,
                type=row["tipo_sucursal"],
                empresa=company

            )
            branch.save()

        try:
            contact = Contact.objects.get(phone__exact=row["telefono_gerente"], tenant=tenant)
            branch.contacto = contact
            branch.save()

        except Contact.DoesNotExist:
            contact = Contact(fullname=row["nombre_gerente"], phone=row["telefono_gerente"], email=None, tenant=tenant)
            contact.save()
            branch.contacto = contact
            branch.save()

        except Exception as e:

            print(e)


def track_dac_delivery(tracking_code, tenant_id):

    try:
        tenant_configuration = get_tenant_config_by_id(tenant_id)
    except Exception as e:
        print(f"Config not found for tenant_id {tenant_id}: {e}")
        return None

    if tenant_configuration.dac_integration_enabled:
        print(f"Checking DAC {tenant_configuration.tenant} deliveries...")

        dac_conn = DacApi(
            url=tenant_configuration.dac_base_url,
            user=tenant_configuration.dac_user,
            password=tenant_configuration.dac_password
        )

        rastreo = dac_conn.rastrear(rastreo=tracking_code)
        dac_conn.end_session()

        return rastreo

    else:
        return None


def validate_and_standardize_phone(phone_number, default_region="US"):
    try:
        # Parse the number with a default region
        parsed_number = parse(phone_number, default_region)

        # Check if the number is possible and valid
        if not is_possible_number(parsed_number) or not is_valid_number(parsed_number):
            raise ValidationError("Invalid phone number.")

        # Standardize the number
        standardized_number = geocoder.description_for_number(parsed_number, "en")
        standardized_format = format_number(parsed_number, PhoneNumberFormat.E164)

        return standardized_format, standardized_number
    except Exception as e:
        raise ValidationError(f"Could not validate phone number. Error: {str(e)}")