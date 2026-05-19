# Prompt Backend — Panel SUPER_ADMIN y activación manual de tenants

Fecha: 2026-05-18  
Proyecto: Gym Management Backend

## Objetivo

Implementar un flujo administrativo para que el dueño del sistema pueda gestionar tenants desde el backend:

- ver tenants registrados;
- ver tenants pendientes de pago;
- activar tenants por pago manual;
- renovar membresías/suscripciones;
- cambiar plan;
- dar de baja/suspender tenants;
- registrar pagos en efectivo o transferencia sin usar pasarela externa.

Este flujo NO reemplaza PayPhone/Kushki. Es el flujo manual oficial para pagos recibidos directamente por el dueño del sistema.

---

## Concepto principal

Debe existir un usuario/rol superior al tenant:

```txt
SUPER_ADMIN
```

Este usuario representa al dueño del sistema SaaS, no al dueño de un gimnasio.

Diferencia importante:

```txt
GERENTE / ADMIN / RECEPCIONISTA -> pertenecen a un tenant/gimnasio
SUPER_ADMIN -> administra la plataforma completa
```

El `SUPER_ADMIN` puede ver y operar tenants. Los usuarios normales NO.

---

## Regla de oro

Nunca activar un tenant editando directamente su estado sin registrar pago.

Incorrecto:

```txt
Actualizar tenant.subscriptionStatus = ACTIVE directamente
```

Correcto:

```txt
Crear payment manual PAID -> activar/renovar tenant
```

Todo debe dejar trazabilidad:

- quién lo activó;
- cuándo;
- monto;
- método;
- plan;
- referencia;
- observación.

---

## Modelo recomendado: payments

Crear una colección nueva:

```txt
payments
```

Documento ejemplo para pago manual:

```json
{
  "paymentId": "uuid",
  "tenantId": "uuid-del-tenant",
  "businessCode": "mi-gimnasio",
  "businessName": "Mi Gimnasio",
  "plan": "PREMIUM",
  "amount": 30,
  "currency": "USD",
  "method": "manual_bank_transfer",
  "source": "MANUAL",
  "status": "PAID",
  "months": 1,
  "reference": "Transferencia Banco Pichincha #12345",
  "notes": "Pago confirmado por WhatsApp",
  "confirmedBy": "super_admin_username",
  "confirmedAt": "2026-05-18T20:00:00Z",
  "createdAt": "2026-05-18T20:00:00Z"
}
```

Métodos sugeridos:

```txt
manual_cash
manual_bank_transfer
manual_other
payphone
kushki
```

Estados sugeridos:

```txt
PENDING
PENDING_REVIEW
PAID
REJECTED
REFUNDED
CANCELLED
```

---

## Estados del tenant

Usar o extender `subscriptionStatus`:

```txt
PENDING_PAYMENT
ACTIVE
EXPIRED
SUSPENDED
CANCELLED
```

Si actualmente solo existen algunos estados, agregar los necesarios con cuidado para no romper compatibilidad.

---

## Lógica de activación

### Nuevo tenant pendiente

Cuando el usuario se registra pero todavía no pagó:

```txt
subscriptionStatus = PENDING_PAYMENT
plan = BASIC/PREMIUM seleccionado
subscriptionStartDate = null
subscriptionEndDate = null
```

Cuando SUPER_ADMIN registra pago manual:

```txt
subscriptionStatus = ACTIVE
subscriptionStartDate = hoy
subscriptionEndDate = hoy + meses pagados
```

---

### Renovación

Si el tenant sigue activo:

```txt
subscriptionEndDate = subscriptionEndDate actual + meses pagados
```

Si el tenant ya expiró:

```txt
subscriptionStartDate = hoy
subscriptionEndDate = hoy + meses pagados
subscriptionStatus = ACTIVE
```

---

### Dar de baja / suspender

SUPER_ADMIN puede cambiar:

```txt
subscriptionStatus = SUSPENDED
```

o:

```txt
subscriptionStatus = CANCELLED
```

Diferencia recomendada:

- `SUSPENDED`: pausa temporal por deuda, soporte o revisión.
- `CANCELLED`: baja definitiva o cancelación del cliente.

---

## Endpoints recomendados

Crear router nuevo:

```txt
backend/app/routers/admin_tenants.py
```

Prefijo:

```txt
/api/admin/tenants
```

### Listar tenants

```txt
GET /api/admin/tenants
```

Query params:

```txt
status=ACTIVE|PENDING_PAYMENT|EXPIRED|SUSPENDED|CANCELLED
plan=BASIC|PREMIUM
search=nombre/email/businessCode
skip=0
limit=50
```

Debe retornar:

```json
{
  "tenants": [],
  "total": 10
}
```

---

### Ver detalle de tenant

```txt
GET /api/admin/tenants/{tenantId}
```

Debe incluir:

- datos del negocio;
- owner;
- plan;
- estado;
- fechas de suscripción;
- último pago;
- historial de pagos.

---

### Activar o renovar con pago manual

```txt
POST /api/admin/tenants/{tenantId}/manual-payment
```

Body:

```json
{
  "plan": "PREMIUM",
  "amount": 30,
  "currency": "USD",
  "method": "manual_bank_transfer",
  "months": 1,
  "reference": "Transferencia Banco Pichincha #12345",
  "notes": "Pago confirmado por WhatsApp"
}
```

Debe hacer en una sola operación lógica:

1. Validar que el usuario actual sea `SUPER_ADMIN`.
2. Buscar tenant.
3. Crear registro en `payments` con status `PAID`.
4. Activar o renovar tenant.
5. Retornar tenant actualizado + payment creado.

---

### Suspender tenant

```txt
POST /api/admin/tenants/{tenantId}/suspend
```

Body:

```json
{
  "reason": "Pago vencido / revisión administrativa"
}
```

Debe cambiar:

```txt
subscriptionStatus = SUSPENDED
```

---

### Reactivar tenant sin pago

Evitarlo en lo posible. Si se implementa, debe exigir motivo fuerte.

```txt
POST /api/admin/tenants/{tenantId}/reactivate
```

Body:

```json
{
  "reason": "Corrección administrativa"
}
```

Debe crear evento/audit log. No usarlo como flujo normal de cobro.

---

### Cancelar tenant

```txt
POST /api/admin/tenants/{tenantId}/cancel
```

Body:

```json
{
  "reason": "Cliente canceló servicio"
}
```

Debe cambiar:

```txt
subscriptionStatus = CANCELLED
```

---

### Historial de pagos

```txt
GET /api/admin/tenants/{tenantId}/payments
```

Debe retornar todos los pagos del tenant.

---

## Seguridad obligatoria

Crear dependencia:

```py
require_super_admin
```

Debe validar:

- token JWT válido;
- rol `SUPER_ADMIN`;
- este usuario no debe depender de un tenant común.

Ejemplo conceptual:

```py
if current_user.role != UserRole.SUPER_ADMIN:
    raise HTTPException(status_code=403, detail="Solo SUPER_ADMIN")
```

No permitir que un `GERENTE` de gimnasio use estos endpoints.

---

## Auditoría recomendada

Crear colección opcional:

```txt
admin_audit_logs
```

Ejemplo:

```json
{
  "action": "TENANT_MANUAL_PAYMENT",
  "tenantId": "uuid",
  "performedBy": "super_admin_username",
  "metadata": {
    "amount": 30,
    "method": "manual_bank_transfer",
    "reference": "..."
  },
  "createdAt": "date"
}
```

Mínimo, el payment debe guardar `confirmedBy` y `confirmedAt`.

---

## Integración futura con PayPhone/Kushki

Cuando se agregue pago automático, debe reutilizar la misma lógica interna:

```txt
payment PAID -> activar/renovar tenant
```

La diferencia será el `source`:

```txt
MANUAL
PAYPHONE
KUSHKI
```

Así no duplicás reglas de negocio.

---

## Criterios de aceptación

- [ ] Existe rol `SUPER_ADMIN`.
- [ ] Existe endpoint para listar tenants.
- [ ] Existe endpoint para ver detalle de tenant.
- [ ] Existe colección `payments`.
- [ ] Activación manual crea payment `PAID`.
- [ ] Activación manual actualiza estado y fechas del tenant.
- [ ] Renovación extiende fecha correctamente.
- [ ] Suspensión/baja cambia estado del tenant.
- [ ] Solo `SUPER_ADMIN` puede usar endpoints admin.
- [ ] El flujo automático futuro puede reutilizar la misma lógica.

## Resultado esperado

El dueño del sistema puede operar pagos externos al sistema — efectivo o transferencia — sin romper la trazabilidad ni saltarse la lógica de suscripción.
