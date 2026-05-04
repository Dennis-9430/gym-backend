# PROMPT — REESTRUCTURACIÓN DEL FLUJO SaaS MULTI-TENANT DEL SISTEMA DE GIMNASIO

## CONTEXTO GENERAL

El proyecto es un sistema SaaS multi-tenant para gimnasios.

Cada gimnasio es un tenant independiente.

El sistema ya tiene implementado gran parte del backend y frontend, incluyendo:

* tenants
* employees
* clients
* services
* products
* sales
* invoices
* attendance
* reports
* configuración (/config)
* autenticación
* roles

Actualmente el flujo de registro y creación de usuarios no concuerda correctamente con la arquitectura SaaS final.

El objetivo es reorganizar y mejorar el flujo completo para que:

* sea profesional
* escalable
* seguro
* compatible con pagos automáticos
* compatible con Stripe webhook
* compatible con recuperación de contraseña
* compatible con owner/admin principal
* compatible con futuras renovaciones de planes

---

# OBJETIVO PRINCIPAL

Reestructurar completamente el flujo de:

* registro
* creación de tenant
* creación de usuario owner/admin
* configuración inicial
* activación por pago
* login
* recuperación de contraseña
* restricciones del owner principal

El sistema debe quedar preparado para:

* integración futura con Stripe
* pagos automáticos
* webhook de confirmación
* renovaciones
* upgrades de planes
* multi-tenant real

---

# ARQUITECTURA GENERAL

# LANDING PAGE

La landing page pública mostrará:

* información del sistema
* características
* screenshots
* beneficios
* planes
* precios
* demos
* botón de registro

Dominio ejemplo:

```txt
https://misistema.com
```

---

# APP SaaS

La aplicación principal del sistema debe estar separada de la landing.

Dominio ejemplo:

```txt
https://app.misistema.com
```

---

# FLUJO CORRECTO DEL SISTEMA

# PASO 1 — USUARIO SELECCIONA PLAN

Desde la landing:

* BASIC
* PREMIUM

Al seleccionar:

```txt
/register?plan=basic
```

ó:

```txt
/register?plan=premium
```

---

# PASO 2 — FORMULARIO DE REGISTRO

El formulario de registro debe incluir:

## DATOS DEL NEGOCIO

* businessName
* businessPhone
* businessAddress
* businessRuc

## DATOS DEL OWNER PRINCIPAL

* documentNumber
* firstName
* lastName
* email
* password

## DATOS DEL PLAN

* selectedPlan

---

# IMPORTANTE

El formulario de registro debe compartir información con:

* tenants
* employees

Porque:

* tenant = negocio
* employee owner = dueño principal del sistema

---

# EJEMPLO DE CREACIÓN

## TENANT

```json
{
  "tenantId": "uuid",
  "businessName": "Gym Power",
  "businessPhone": "099999999",
  "businessAddress": "",
  "businessRuc": "",
  "email": "gym@gmail.com",
  "plan": "PREMIUM",
  "subscriptionStatus": "ACTIVE"
}
```

---

## EMPLOYEE OWNER

```json
{
  "tenantId": "uuid",
  "documentNumber": "0700000000",
  "firstName": "Dennis",
  "lastName": "Pinzon",
  "email": "gym@gmail.com",
  "username": "gym@gmail.com",
  "password": "bcrypt_hash",
  "role": "ADMIN",
  "isOwner": true,
  "isActive": true
}
```

---

# REGLAS IMPORTANTES

# OWNER PRINCIPAL

El primer usuario creado automáticamente debe:

```json
{
  "role": "ADMIN",
  "isOwner": true,
  "isActive": true
}
```

---

# DIFERENCIA ENTRE ADMIN Y OWNER

## ADMIN NORMAL

Puede:

* gestionar clientes
* gestionar ventas
* gestionar empleados
* ver reportes

Pero NO es el dueño principal.

---

## OWNER

Es el dueño principal del tenant.

Debe existir SOLO UNO por tenant.

Tiene permisos especiales.

---

# RESTRICCIONES DEL OWNER

El OWNER NO puede:

* eliminarse
* desactivarse
* cambiar tenantId
* cambiar email principal desde employees
* cambiar email principal desde config
* modificar plan manualmente
* modificar subscriptionStatus manualmente

El OWNER SÍ puede:

* cambiar contraseña
* editar nombre
* editar datos secundarios
* editar configuración del negocio

---

# CONFIGURACIÓN (/config)

La sección /config debe reflejar automáticamente los datos del tenant.

Los datos ingresados en el registro deben aparecer automáticamente.

Ejemplo:

* businessName
* businessPhone
* businessAddress
* businessRuc
* openingHour
* closingHour
* taxRate
* currency

---

# IMPORTANTE

Los campos vacíos pueden ser completados luego.

---

# RELACIÓN ENTRE REGISTER Y CONFIG

Toda la información del formulario inicial debe reflejarse automáticamente en:

```txt
/config
```

Porque /config representa los datos globales del tenant.

---

# LOGIN

El login debe funcionar usando:

```txt
email + password
```

El email debe pertenecer al employee.

---

# RECUPERAR CONTRASEÑA

Implementar:

```txt
/forgot-password
```

Flujo:

1. usuario ingresa email
2. backend genera token temporal
3. token expira en 15 minutos
4. email enviado
5. usuario crea nueva contraseña

---

# SEGURIDAD

# PASSWORDS

Nunca guardar passwords en texto plano.

Siempre usar:

```txt
bcrypt
```

---

# WEBHOOK FUTURO

Aunque el webhook aún no esté implementado completamente, la arquitectura debe prepararse desde ahora.

---

# FLUJO FUTURO REAL

# LANDING

↓

# REGISTRO

↓

# PAGO STRIPE

↓

# WEBHOOK CONFIRMA

↓

# CREAR TENANT

↓

# CREAR OWNER ADMIN

↓

# CREAR SUBSCRIPTION

↓

# ACTIVAR SISTEMA

↓

# LOGIN

---

# IMPORTANTE PARA DESARROLLO ACTUAL

Actualmente aún NO existe:

* landing final
* integración Stripe
* webhook completo
* confirmación automática de pago

Pero se necesita empezar pruebas YA.

---

# MODO TEMPORAL DE DESARROLLO

Implementar un modo temporal para pruebas.

Cuando se registre un usuario:

* crear tenant automáticamente
* crear owner automáticamente
* activar subscription automáticamente
* permitir login inmediato

Simular:

```json
{
  "subscriptionStatus": "ACTIVE"
}
```

---

# IMPORTANTE

Este modo temporal debe estar separado y preparado para ser reemplazado posteriormente por el webhook real.

---

# ARQUITECTURA RECOMENDADA

# tenants

Representa el negocio.

Debe contener:

```json
{
  "tenantId": "uuid",
  "businessName": "",
  "businessPhone": "",
  "businessAddress": "",
  "businessRuc": "",
  "plan": "BASIC | PREMIUM",
  "subscriptionStatus": "PENDING | ACTIVE | EXPIRED",
  "ownerEmployeeId": "employee_id"
}
```

---

# employees

Representa usuarios internos del tenant.

Debe contener:

```json
{
  "tenantId": "",
  "documentNumber": "",
  "firstName": "",
  "lastName": "",
  "email": "",
  "password": "",
  "role": "ADMIN | EMPLOYEE",
  "isOwner": true,
  "isActive": true
}
```

---

# subscriptions

Crear colección real para manejo futuro.

No depender solamente de:

```json
{
  "subscriptionStatus": "ACTIVE"
}
```

---

# subscriptions ejemplo

```json
{
  "tenantId": "",
  "plan": "PREMIUM",
  "status": "ACTIVE",
  "startDate": "",
  "endDate": "",
  "paymentProvider": "stripe",
  "paymentId": "",
  "autoRenew": true
}
```

---

# VALIDACIONES IMPORTANTES

# REGISTER

Validar:

* email único
* documentNumber único por tenant
* password segura
* businessName requerido
* selectedPlan requerido

---

# LOGIN

Validar:

* employee.isActive
* tenant.subscriptionStatus

---

# SI SUBSCRIPTION EXPIRED

Bloquear acceso parcial o total.

---

# RESTRICCIONES POR PLAN

# BASIC

* sin empleados múltiples
* sin reportes avanzados
* sin configuraciones premium

---
# REGLAS DEL PLAN BASIC

El plan BASIC solo permite UN usuario dentro del sistema.

Ese usuario corresponde al OWNER principal creado automáticamente durante el registro.

Ejemplo:

```json
{
    "plan": "BASIC",
  "status": "ACTIVE",
  "role": "ADMIN",
  "isOwner": true
}

# PREMIUM

* empleados
* reportes
* configuración completa
* futuras automatizaciones

---

# IMPORTANTE PARA IA

NO romper:

* autenticación actual
* tenant isolation
* relaciones existentes
* permisos existentes
* endpoints actuales

---

# OBJETIVO DEL REFACTOR

Mejorar:

* arquitectura SaaS
* flujo de creación
* estructura multi-tenant
* separación owner/admin
* escalabilidad futura
* seguridad
* mantenibilidad

---

# IMPLEMENTACIÓN ESPERADA

La IA debe:

1. analizar arquitectura actual
2. detectar inconsistencias
3. mejorar flujo actual
4. reorganizar entidades
5. mantener compatibilidad
6. evitar romper funcionalidades existentes
7. preparar sistema para Stripe webhook futuro
8. preparar recuperación de contraseña
9. preparar owner/admin correctamente
10. centralizar datos del tenant en /config

---

# RESULTADO FINAL ESPERADO

El sistema debe quedar preparado para:

* SaaS real
* pagos automáticos
* Stripe
* escalabilidad
* múltiples tenants
* múltiples empleados
* renovaciones futuras
* upgrades
* seguridad profesional
* login robusto
* recuperación de contraseña
* owner principal protegido
* arquitectura limpia
