# PgBouncer – connection pooler para PostgreSQL

PgBouncer se sitúa entre la aplicación y PostgreSQL: la app se conecta a PgBouncer (puerto **6432**) y PgBouncer mantiene un pool de conexiones a Postgres (puerto 5432).

## 1. Configuración

1. Copiar los `.example` y ajustar:
   ```bash
   cp pgbouncer.ini.example pgbouncer.ini
   cp userlist.txt.example userlist.txt
   ```

2. **pgbouncer.ini**
   - En `[databases]`: sustituir `POSTGRES_HOST` por el hostname o IP de tu servidor PostgreSQL.
   - Opcional: cambiar `dbname`, `port`, `pool_mode`, `default_pool_size`.

3. **userlist.txt**
   - Sustituir `POSTGRES_USER` por el usuario de Postgres.
   - Generar hash MD5 del password:
     ```bash
     echo -n "TU_PASSWORDPOSTGRES_USER" | md5sum
     ```
     (password + usuario, sin espacio). En userlist poner:
     `"postgres_user" "md5" + el hash de 32 caracteres`.

## 2. Crear PgBouncer con Docker

Imagen oficial o compatible (ej. `edoburu/pgbouncer` o `bitnami/pgbouncer`):

```bash
# Con archivos locales (pgbouncer.ini y userlist.txt en el directorio actual)
docker run -d --name pgbouncer \
  -p 6432:6432 \
  -v "$(pwd)/pgbouncer.ini:/etc/pgbouncer/pgbouncer.ini:ro" \
  -v "$(pwd)/userlist.txt:/etc/pgbouncer/userlist.txt:ro" \
  edoburu/pgbouncer:latest
```

O con variables de entorno (dependiendo de la imagen):

```bash
docker run -d --name pgbouncer \
  -p 6432:6432 \
  -e DATABASE_URL="postgres://user:pass@POSTGRES_HOST:5432/moio_greenfield" \
  -e POOL_MODE=transaction \
  edoburu/pgbouncer:latest
```

Comprobar:

```bash
docker logs pgbouncer
psql "postgres://user:pass@localhost:6432/moio_greenfield" -c "SELECT 1"
```

## 3. Crear PgBouncer en Kubernetes

Si Postgres está fuera del cluster, PgBouncer puede ir en un Deployment que apunte a ese Postgres (por IP/hostname o ExternalName Service).

1. **ConfigMap** con `pgbouncer.ini` (sin secretos):

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: pgbouncer-config
  namespace: moio-greenfield
data:
  pgbouncer.ini: |
    [databases]
    moio_greenfield = host=TU_POSTGRES_HOST port=5432 dbname=moio_greenfield
    [pgbouncer]
    listen_addr = *
    listen_port = 6432
    auth_type = md5
    auth_file = /etc/pgbouncer/userlist.txt
    pool_mode = transaction
    max_client_conn = 500
    default_pool_size = 25
```

2. **Secret** con `userlist.txt` (usuario + hash MD5):

```bash
kubectl create secret generic pgbouncer-auth -n moio-greenfield \
  --from-file=userlist.txt=./userlist.txt
```

3. **Deployment** (ejemplo):

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pgbouncer
  namespace: moio-greenfield
spec:
  replicas: 1
  selector:
    matchLabels:
      app: pgbouncer
  template:
    metadata:
      labels:
        app: pgbouncer
    spec:
      containers:
        - name: pgbouncer
          image: edoburu/pgbouncer:latest
          ports:
            - containerPort: 6432
          volumeMounts:
            - name: config
              mountPath: /etc/pgbouncer
              readOnly: true
      volumes:
        - name: config
          projected:
            sources:
              - configMap:
                  name: pgbouncer-config
              - secret:
                  name: pgbouncer-auth
---
apiVersion: v1
kind: Service
metadata:
  name: pgbouncer
  namespace: moio-greenfield
spec:
  selector:
    app: pgbouncer
  ports:
    - port: 6432
      targetPort: 6432
```

4. **URL para la app** (en ConfigMap/values del backend):

- Si PgBouncer está en el mismo namespace:  
  `postgres://user:password@pgbouncer:6432/moio_greenfield`
- Si Postgres está fuera y no usas PgBouncer en K8s:  
  usa la URL directa a PgBouncer donde lo tengas (host:6432).

## 4. Resumen

| Dónde corre PgBouncer | DATABASE_URL para la app |
|------------------------|---------------------------|
| Docker en el mismo host | `postgres://user:pass@localhost:6432/moio_greenfield` |
| K8s Service `pgbouncer` | `postgres://user:pass@pgbouncer.moio-greenfield.svc:6432/moio_greenfield` |
| Servidor/VPS externo     | `postgres://user:pass@pgbouncer-host:6432/moio_greenfield` |

Sustituir `user`, `pass` y el host por tus valores reales.
