# Revisión backend clonado — pagos pendientes por transferencia

**Fecha:** 2026-05-25  
**Ruta revisada:** `C:\Users\Dennis\Documents\proyectos-codex\gym-backend`  
**Objetivo:** validar los cambios del backend clonado para soportar registro con transferencia pendiente, aprobación/rechazo por SUPER_ADMIN y preparación para producción.

## Aclaración sobre URLs ya desplegadas

El pendiente anterior de:

- `VITE_API_URL` real
- `ALLOWED_ORIGINS` real

queda **marcado como resuelto a nivel de configuración de plataforma** según lo indicado: frontend en Vercel, backend en Render y base de datos en MongoDB Atlas.

Lo que sí revisé en código es que el backend soporte `ALLOWED_ORIGINS` por variable de entorno. El código en `app/main.py` está bien orientado: si `ALLOWED_ORIGINS` no es `*`, activa `allow_credentials=True` y usa dominios específicos.

**Importante:** no puedo confirmar el valor real cargado en Render desde el código local. Eso se verifica en el dashboard de Render o probando la URL pública.

---

## Estado Git del backend clonado

Hay cambios locales sin commit en:

```txt
M app/models/tenant.py
M app/routers/admin.py
M app/routers/tenants.py
```

Estos cambios son justamente los relacionados al flujo de pagos pendientes.

---

## Qué se implementó bien

### 1. El modelo ya acepta métodos de pago nuevos

En `app/models/tenant.py` se agregó:

```py
PaymentMethod.CARD
PaymentStatus.PENDING
PaymentStatus.PAID
PaymentStatus.REJECTED
PaymentStatus.CANCELLED
```

También se agregaron campos al registro:

```py
paymentMethod
cardToken
transferReference
receiptUrl
paymentMonths
```

Esto conecta mejor con el frontend, que ya manda `paymentMethod`, `cardToken` y `transferReference` desde `Register.tsx`.

### 2. Transferencia ahora crea payment pendiente

En `app/routers/tenants.py`, si el registro llega con:

```py
paymentMethod == TRANSFER
```

se crea un documento en `tenant_payments` con:

```txt
method: TRANSFER
status: PENDING
source: TRANSFER_ONLINE
```

Y el tenant queda como `PENDING_PAYMENT`.

Esto es conceptualmente correcto.

### 3. SUPER_ADMIN ya tiene endpoints para pagos pendientes

En `app/routers/admin.py` se agregaron:

```txt
GET  /api/admin/payments/pending
POST /api/admin/tenants/{tenant_id}/approve-payment
POST /api/admin/tenants/{tenant_id}/reject-payment
```

Esto corrige el problema anterior donde el frontend tenía pantalla de pagos pendientes pero el backend no tenía endpoints.

---

## Problemas críticos antes de producción

### 1. El pago con tarjeta es un stub que activa tenants automáticamente

En `app/routers/tenants.py`, si llega:

```py
paymentMethod == CARD
```

el backend crea pago `PAID` y activa el tenant inmediatamente.

Eso sirve para prueba local, pero **NO puede estar activo en producción real**.

El frontend genera un token simulado:

```ts
tok_sim_...
```

Entonces cualquier persona podría registrar una cuenta, elegir tarjeta y quedar activa sin pagar realmente.

**Recomendación obligatoria:**

- En producción, `CARD` debe quedar bloqueado hasta tener pasarela real.
- Solo activar tenant por tarjeta cuando un webhook del proveedor confirme pago real.
- Mientras tanto, permitir solo `TRANSFER` pendiente o registro demo controlado.

---

### 2. `paymentMonths` no tiene validación segura

En `TenantCreate`:

```py
paymentMonths: int = 1
```

No tiene `Field(ge=1, le=24)`.

**Riesgo:** un usuario puede enviar:

```json
{ "paymentMonths": -100 }
```

y generar montos negativos o fechas inválidas.

**Recomendación:**

```py
paymentMonths: int = Field(default=1, ge=1, le=24)
```

---

### 3. Aprobar/rechazar usa `tenant_id`, no `payment_id`

Los endpoints actuales aprueban el pago pendiente más reciente del tenant:

```py
find_one({"tenantId": tenant_id, "method": "TRANSFER", "status": "PENDING"}, sort=[("createdAt", -1)])
```

Funciona si cada tenant tiene un solo pago pendiente, pero falla si hay múltiples intentos.

**Riesgo:** el SUPER_ADMIN puede aprobar/rechazar un pago distinto al que vio en pantalla.

**Recomendación:** cambiar contrato a:

```txt
POST /api/admin/payments/{payment_id}/approve
POST /api/admin/payments/{payment_id}/reject
```

El frontend ya tiene `payment.id`, así que debería enviar ese ID.

---

### 4. Dashboard y detalle de tenant pueden sumar pagos PENDING/REJECTED como ingresos

En `admin_dashboard`, el pipeline de ingresos mensuales suma `tenant_payments` por fecha, pero no filtra:

```txt
status = PAID
```

En `admin_get_tenant`, el `total_paid` también suma sin filtrar por `PAID`.

**Riesgo:** una transferencia pendiente o rechazada puede inflar ingresos.

**Recomendación:** agregar filtro:

```py
{"$match": {"createdAt": {"$gte": month_start}, "status": "PAID"}}
```

y en resumen de tenant:

```py
{"$match": {"tenantId": tenant_id, "status": "PAID"}}
```

---

### 5. Registro + pago no es atómico

En `register_tenant`, primero se crea tenant, employee, user y services. Luego se crea payment.

Si falla la creación del payment, puede quedar tenant parcialmente creado.

**Recomendación producción:** usar transacción MongoDB si Atlas/cluster lo soporta, o implementar compensación/rollback manual.

---

### 6. Transferencia no exige referencia ni comprobante

El frontend marca referencia como opcional y manda `transferReference` solo si existe.

Backend permite crear pago pendiente sin referencia ni comprobante.

**Riesgo:** SUPER_ADMIN verá pagos pendientes difíciles de validar.

**Recomendación:** para transferencia real pedir al menos uno:

- `transferReference`, o
- `receiptUrl`, o
- comprobante subido a storage.

Para demo puede quedar opcional, pero para producción real no.

---

### 7. `receiptUrl` es confiado desde el cliente

Backend acepta `receiptUrl` como string enviado por frontend.

**Riesgo:** URLs arbitrarias o maliciosas.

**Recomendación:** si se va a usar comprobante, subir archivo a storage controlado por backend y guardar solo URL generada por el sistema.

---

### 8. `.env.production` local sigue siendo plantilla con secreto inseguro

Aunque Render tenga variables reales, el archivo local contiene:

```txt
JWT_SECRET_KEY=gym-mgmt-2026-k8s-prod-secret-key-change-in-production
```

Esto no debe usarse como secreto real.

**Recomendación:** renombrar a `.env.production.example` o dejarlo claramente como plantilla sin valores sensibles.

---

## Validaciones ejecutadas

### `git diff --check`

Resultado: falló por espacios finales en:

```txt
app/routers/tenants.py:285 trailing whitespace
app/routers/tenants.py:288 trailing whitespace
```

No es crítico funcionalmente, pero antes de commit conviene limpiarlo.

### Tests backend

No ejecuté tests porque en este entorno no hay Python funcional configurado para correr `pytest`.

---

## Recomendaciones concretas de corrección

### Backend

1. Bloquear `CARD` en producción hasta webhook real.
2. Validar `paymentMonths` con `Field(default=1, ge=1, le=24)`.
3. Cambiar approve/reject para trabajar por `payment_id`, no por `tenant_id`.
4. Filtrar ingresos y `total_paid` solo por `status: PAID`.
5. Exigir referencia o comprobante para transferencia real.
6. Agregar `updatedAt` al crear payment pendiente.
7. Limpiar trailing whitespace.
8. Agregar tests para:
   - registro por transferencia crea payment `PENDING`;
   - login bloqueado mientras está `PENDING_PAYMENT`;
   - SUPER_ADMIN lista pagos pendientes;
   - approve activa tenant y marca payment `PAID`;
   - reject marca `REJECTED` y no activa tenant;
   - ingresos no cuentan `PENDING` ni `REJECTED`.

### Frontend

1. Si `CARD` sigue siendo simulado, ocultarlo o marcarlo como demo.
2. Para transferencia, pedir referencia obligatoria o comprobante.
3. Cambiar approve/reject para enviar `payment.id` cuando backend lo soporte.
4. Mostrar mensaje claro después de registro por transferencia:
   - “Tu cuenta fue creada, pendiente de aprobación de pago.”
   - No decir “inicia sesión” como si ya estuviera activa.

---

## Veredicto

El flujo de transferencia pendiente **ya está mucho más cerca de lo correcto** que antes. Ahora sí existe el contrato base frontend/backend.

Pero todavía **no está listo para producción real** por 4 puntos fuertes:

1. tarjeta simulada activa tenants;
2. approve/reject debería ir por payment ID;
3. ingresos cuentan pagos no pagados si no se filtra `PAID`;
4. `paymentMonths` no está validado.

Mi recomendación: corregir esos puntos antes de deployar esta rama/clon a producción.
