import pandas as pd
import numpy as np
import re
from crm.models import Customer, Address, Tag, Product

HEADER_MIN_NONEMPTY = 2       # tweak for your files
HEADER_UNIQ_THRESHOLD = 0.6   # fraction of unique cells


def import_addresses(df, tenant):

    for index, row in df.iterrows():

        customer_name = row.get('customer_name', "")
        client_ext_ref = str(row.get("CodigoExt", "")).split(".")[0]
        id_type = row.get("TipoID", "")
        tax_id = str(row.get("ID", "")).split(".")[0]
        location = row.get("Geo", "")

        address_name = row.get("Nombre", "")
        legal_name = row.get("Razon", "")
        address = row.get("Direccion", "")
        address_internal = row.get("Internal", "")
        city = row.get("Ciudad", "")
        state = row.get("Departamento", "")
        country = row.get("Pais", "")
        postalcode = row.get("CP", "")
        type_location = row.get("Tipo_Direccion", "")
        comments = row.get("Comentarios", "")
        invoice_address = row.get("Direccion_Factura", False)
        delivery_address = row.get("Direccion_Entrega", True)
        enabled = row.get("Activo", True)
        branch_code = str(row.get("Sucursal", "")).split(".")[0]
        longitude = 0
        latitude = 0

        if pd.notna(location):
            latitude = str(location).split(",")[0]
            longitude = str(location).split(",")[1]

        if tax_id != 'nan':
            print(f'Cliente {legal_name} {id_type}:{tax_id} | Cliente:{client_ext_ref}')
            print(f'Direccion: {address} | Sucursal: {branch_code}' )

            try:

                if id_type == "RUT":
                    client = Customer.objects.get(tax_id__exact=tax_id)
                else:
                    client = Customer.objects.get(national_document__exact=tax_id)

            except Customer.DoesNotExist:
                if id_type == "RUT":
                    customer_type = "Business"
                    client = Customer.objects.create(type=customer_type,
                                                     legal_name=legal_name,
                                                     tax_id=tax_id,
                                                     name=customer_name,
                                                     external_id=client_ext_ref,
                                                     tenant=tenant)

                else:
                    customer_type = "Person"
                    client = Customer.objects.create(type=customer_type,
                                                     legal_name=legal_name,
                                                     name=customer_name,
                                                     national_document=tax_id,
                                                     external_id=client_ext_ref,
                                                     tenant=tenant)

                client.save()

            try:
                existing_address = Address.objects.get(branch_code=branch_code, customer=client)
                existing_address.name = address_name
                existing_address.address = address
                existing_address.longitude = longitude
                existing_address.latitude = latitude
                existing_address.address_internal = address_internal
                existing_address.city = city
                existing_address.state = state
                existing_address.country = country
                existing_address.postalcode = postalcode
                existing_address.type_location = type_location
                existing_address.comments = comments
                existing_address.invoice_address = invoice_address
                existing_address.delivery_address = delivery_address
                existing_address.enabled = enabled
                existing_address.save()

            except Address.DoesNotExist:

                new_address = Address.objects.create(branch_code=branch_code,
                                                 name=address_name,
                                                 address=address,
                                                 customer=client,
                                                 latitude=latitude,
                                                 longitude=longitude,
                                                 address_internal=address_internal,
                                                 city=city,
                                                 state=state,
                                                 country=country,
                                                 postalcode=postalcode,
                                                 type_location=type_location,
                                                 comments=comments,
                                                 invoice_address=invoice_address,
                                                 delivery_address=delivery_address,
                                                 enabled=enabled
                                                 )
                new_address.save()


def import_customers(df, tenant):
    pass


def import_products(df, tenant):

    for index, row in df.iterrows():

        item = {

            "name": row.get("name"),
            "description": row.get("description"),
            "price": row.get("price"),
            "sale_price": row.get("sale_price"),
            "brand": row.get("brand"),
            "sku": row.get("sku"),
            "product_type": row.get("product_type"),
            "category": row.get("category"),
            "price_currency": row.get("price_currency"),
            "tenant": tenant
        }
        prod = Product.objects.update_or_create(**item)
        prod.save()


def import_leads(df, tenant):
    pass


def import_contacts(df, tenant):
    pass


def import_tags(df, tenant):

    for index, row in df.iterrows():

        name = row.get('name', "")
        description = row.get("description", "")
        if description == 'nan':
            description = ''

        try:
            tag = Tag.objects.get(name=name)

            tag.description = description
            tag.tenant = tenant
            tag.save()

        except Tag.DoesNotExist:

            tag = Tag.objects.create(name=name, description=description, tenant=tenant)
            tag.save()

        print(tag.name)

# ================  CAMPAIGN DATA ================


def import_campaign_data(df, tenant):

    for index, row in df.iterrows():
        print(row)


def read_any(file_path_or_buffer, sheet=None):
    name = str(file_path_or_buffer)
    if name.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(file_path_or_buffer, header=None, sheet_name=sheet)
    else:
        # default to CSV
        return pd.read_csv(file_path_or_buffer, header=None, dtype=str, keep_default_na=False, na_values=[""])


def detect_header_row(raw_df: pd.DataFrame) -> int:
    """
    Heuristic: pick the first row with enough non-empty cells AND high uniqueness,
    which typically looks like a header row (vs titles/notes).
    """
    best_row = 0
    best_score = -1
    for i in range(min(len(raw_df), 25)):  # only scan first N rows
        row = raw_df.iloc[i].astype(str).str.strip()
        nonempty = (row != "") & (row.str.lower() != "nan")
        nonempty_count = int(nonempty.sum())
        unique_ratio = row[nonempty].nunique() / max(nonempty_count, 1)
        score = nonempty_count + (unique_ratio * 2.0)  # weight uniqueness higher

        if nonempty_count >= HEADER_MIN_NONEMPTY and unique_ratio >= HEADER_UNIQ_THRESHOLD and score > best_score:
            best_score = score
            best_row = i
    return best_row


def normalize_column_name(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^0-9a-zA-Z]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:128] or "col"


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    # Standardize column names
    df.columns = [normalize_column_name(c) for c in df.columns]

    # Drop fully empty columns
    df = df.dropna(axis=1, how="all")

    # Trim strings and coerce obvious numerics/dates (safe/forgiving)
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].astype(str).str.strip()
            # convert empty-ish to NaN for consistency
            df[col] = df[col].replace({"": np.nan, "nan": np.nan, "None": np.nan})
        # Try numeric
        try_num = pd.to_numeric(df[col], errors="ignore")
        if try_num.dtype != object:
            df[col] = try_num
            continue
        # Try dates if it smells like a date (very light heuristic)
        if df[col].dropna().astype(str).str.contains(r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4}", regex=True).any():
            try_date = pd.to_datetime(df[col], errors="coerce", dayfirst=True)
            if try_date.notna().sum() >= max(3, int(0.3 * len(df))):
                df[col] = try_date

    # Remove duplicate rows (optional)
    df = df.drop_duplicates()
    return df.reset_index(drop=True)


def load_and_prepare(file_path_or_buffer, sheet=None):
    """
    1) Read with no header.
    2) Detect header row.
    3) Re-read with header.
    4) Clean.
    Returns: (df, header_row_index)
    """
    raw = read_any(file_path_or_buffer, sheet=sheet)
    hdr = detect_header_row(raw)
    df = read_any(file_path_or_buffer, sheet=sheet)
    # Re-read this time with header=hdr
    if hasattr(df, "iloc"):
        # If read_any returned DataFrame already (Excel), re-read with header
        df = read_any(file_path_or_buffer, sheet=sheet)
    # Use pandas engine parameters directly:
    if str(file_path_or_buffer).lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(file_path_or_buffer, header=hdr, sheet_name=sheet)
    else:
        df = pd.read_csv(file_path_or_buffer, header=hdr, dtype=str, keep_default_na=False, na_values=[""])

    df = clean_dataframe(df)
    return df, hdr
