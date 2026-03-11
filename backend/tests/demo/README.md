# Demo data scripts

Scripts para crear y poblar el tenant demo vía API.

## Scripts

| Script | Descripción |
|--------|-------------|
| `setup_demo_tenant.py` | Crea tenant demo + 7 usuarios (2 tenant_admin, 1 manager, 3 member, 1 viewer) |
| `seed_demo_tenant.sh` | 8 customers, 10 contacts, 12 deals (con pipeline) |
| `populate_demo_data.py` | 50 companies, 250 contacts, 500 activities |

## Uso

Desde `backend/`:

```bash
# 1. Crear tenant y usuarios (ejecutar primero)
python tests/demo/setup_demo_tenant.py

# 2. Seed (deals, contacts, accounts)
./tests/demo/seed_demo_tenant.sh

# 3. Populate (volumen grande)
python tests/demo/populate_demo_data.py
```

Requisitos: backend corriendo, migraciones aplicadas.
