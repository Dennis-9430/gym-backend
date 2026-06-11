# Auditoría Técnica Backend Gym Management API — 2026-06-10

## Resumen ejecutivo

**Estado general: Semi Senior → Senior técnico / Pre-producción avanzada**

Desde la auditoría del 2026-06-08 se implementaron aproximadamente 15 PRs que transformaron el backend de forma significativa. Los cambios más notables:

- **Arquitectura**: Routers de 1570 y 800+ líneas reducidos a 385 y 313 respectivamente. Servicios extraídos con DI de DB.
- **Seguridad**: CORS cerrado, Swagger gated, CSRF middleware listo, SecurityHeaders, CatchAllErrorMiddleware.
- **Rate limiting**: Sliding-window con store interface y reglas endpoint-specific (sin Redis aún).
- **Auditoría**: AuditService + colección MongoDB + endpoint SUPER_ADMIN.
- **Base de datos**: TransactionManager, proyecciones, `re.escape`, `to_list(None)` resuelto.
- **Rendimiento**: GZip compress, dashboard paralelizado, TTL cache 30s, índices agregados.
- **DevOps**: Docker multi-stage, docker-compose (Mongo + Redis), CI/CD GitHub Actions.
- **Calidad**: 7 get_tenant_from_header_* unificados en `api/dependencies.py`. Tests: ~5200 líneas.
- **Monetización**: Mock payment provider con checkout + webhook.

### Comparativa de scores

| Categoría | 2026-06-08 | 2026-06-10 | Cambio |
|-----------|-----------|-----------|--------|
| Arquitectura | 62/100 | **82/100** | +20 |
| Seguridad | 55/100 | **78/100** | +23 |
| Escalabilidad | 58/100 | **72/100** | +14 |
| Rendimiento | 60/100 | **72/100** | +12 |
| Calidad del código | 61/100 | **80/100** | +19 |
| Preparación para producción | 52/100 | **70/100** | +18 |

**Puntuación global: 58/100 → 76/100 (+18 puntos)**

### Interpretación

El proyecto pasó de "MVP avanzado / buen portafolio" a "pre-producción seria". Los fundamentos de seguridad, arquitectura y calidad están mucho más sólidos. Los riesgos críticos de la primera auditoría (CORS wildcard, routers monolíticos, sin transacciones, sin auditoría, sin CI/CD) están resueltos.

Lo que separa esto de producción comercial hoy no es mala calidad — son decisiones pendientes de infraestructura y hardening fino. El código está listo para un staging con clientes reales controlados.

---

## 1. Arquitectura

**Score: 82/100**  ✅ Mejorado (62 → 82)

### Lo que se hizo

- **Servicios extraídos**:
  - `TenantAuthService` → register, login, forgot/reset password, renew subscription, tenant config
  - `AdminTenantService` → dashboard, list, get, suspend, cancel, reactivate, toggle biometric, delete tenant
  - `AdminPaymentService` → manual payment, list payments, pending/approve/reject
  - `TenantDemoService` → initialize, seed data, seed attendance, seed owner, cleanup
  - `MockPaymentProvider` → checkout, webhook, verify
  - `AuditService` → log_event, query_logs
- **Router `tenants.py`**: ~385 líneas (era ~1570) — **75% de reducción**
- **Router `admin.py`**: ~313 líneas (era ~800+) — **~60% de reducción**
- **Routers restantes**: employees (431), clients (404), invoices (352), products (226), reports (184), attendance (144) — todos dentro de rango razonable
- **Dependencias unificadas**: `api/dependencies.py` con `get_tenant_from_request`, `require_roles`, `require_plan`, `resolve_tenant`, `get_current_tenant_id`
- **Constructor injection**: todos los servicios reciben `db` en constructor, facilitando tests

### Lo que quedó pendiente

- **⚠️ `app/routers/sales.py`**: 609 líneas — es el router más pesado hoy. Contiene lógica de ventas, facturación, pagos mixtos. No se extrajo a servicio.
- **⚠️ `forgot_password` en `tenants.py`**: Todavía tiene lógica pesada de resolución de tenant, verificación de SUPER_ADMIN, y creación de reset token — no delegada al servicio.
- **⚠️ Lógica DB directa en routers**: `tenants.py:update_current_tenant`, `tenants.py:renew_subscription`, `tenants.py:update_owner` todavía hacen queries DB directas en vez de delegar a servicio.
- **❌ No hay `/api/v1`**: Sigue sin versionado de API.
- **⚠️ `employees.py`**: Tiene `initialize_seed_employees()` inline (líneas 343-447) — esa lógica seed debería vivir en `TenantDemoService`.

### Recomendación

1. Extraer `SalesService` con lógica de: create sale + generate invoice + update inventory + update membership (es un flujo compuesto ideal para transacción).
2. Mover `forgot_password` restante al servicio y simplificar el router.
3. Evaluar si vale la pena `/api/v1` ahora (si hay clientes externos, sí; si solo frontend propio, no urgen).
4. Mover `initialize_seed_employees()` a `TenantDemoService`.

---

## 2. API Design

**Score: 80/100**  ✅ Mejorado (estimado 65→80)

### Lo que se hizo

- **Error format estandarizado**: `{error: {code, detail, message}}` implementado vía `app/models/error.py` + `CatchAllErrorMiddleware` + exception handlers globales.
- **CatchAllErrorMiddleware**: ASGI puro (no BaseHTTPMiddleware) que captura excepciones incluso de middlewares anidados — respeta `response_started`.
- **HTTPException handler**: mapea status code → error code definido.
- **RequestValidationError handler**: 422 con formato estándar.
- **DELETE → 204**: employees, etc. usan `status_code=204`.
- **`page`/`limit`**: listas admin y otras usan parámetros consistentes.
- **`/health` y `/ready`**: endpoints de healthcheck.

### Lo que quedó pendiente

- **⚠️ Algunos endpoints aún no usan error format**: `csrf.py` devuelve `{"detail": "..."}` en vez de `{error: {code, detail, message}}`. `plan_protection.py` también devuelve `{"detail": "..."}`.
- **⚠️ No hay envelope `{data, meta, error}`**: el formato estándar solo cubre errores. Las respuestas exitosas no tienen wrapper uniforme.

### Recomendación

1. Estandarizar respuestas exitosas con un formato común (opcional pero recomendable para documentación).
2. Unificar los middlewares `csrf.py` y `plan_protection.py` para usar el mismo error format.
3. Evaluar agregar `/api/v1` si planeás exponer la API a terceros.

---

## 3. Seguridad

**Score: 78/100**  ✅ Mejorado (55 → 78)

### Lo que se hizo

- **CORS cerrado**: `ALLOWED_ORIGINS` es lista explícita, sin wildcard. Middleware custom que valida origen.
- **Swagger gated**: `docs_url=None`, `redoc_url=None`, `openapi_url=None` cuando `DEBUG=False`.
- **CatchAllErrorMiddleware**: captura errores no manejados y retorna JSON genérico sin leak de `str(e)`.
- **CSRF Middleware**: Double Submit Cookie pattern implementado. Middleware listo.
- **SecurityHeadersMiddleware**: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Strict-Transport-Security, Referrer-Policy.
- **Rate limiting mejorado**: sliding-window con store interface (`RateLimitStore` ABC). Reglas endpoint-specific (login: 5/min, register/forgot/reset: 5/hora).
- **Regex escapado**: `re.escape(search.strip())` en `AdminTenantService.list_tenants`.
- **`isDemo` en TenantCreate**: campo explícito con default False — resuelto el bug crítico de `data.isDemo` no definido.

### Lo que quedó pendiente

- **⚠️ CSRF en warn mode**: `CSRF_ENABLED=False` por defecto. El middleware existe y funciona, pero no bloquea. Para producción hay que activarlo.
- **⚠️ No hay refresh token / token blacklist**: JWT de 24h sin rotación. No se puede revocar un token activo.
- **⚠️ Login no registra audit events**: `TenantAuthService.login()` recibe `audit_service` como opcional, pero `tenants.py:login_tenant()` no lo pasa → no se loguean logins ni intentos fallidos vía audit.
- **⚠️ Fuerza bruta**: rate limiting existe por endpoint, pero no hay bloqueo progresivo por email, captcha, ni detección de patrones de ataque.
- **⚠️ No hay Content-Security-Policy**: SecurityHeadersMiddleware no incluye CSP, que es crítico para prevenir XSS.
- **❌ JWT en respuesta de login**: `login_tenant()` devuelve `accessToken` en el body ademas de setear cookie. Si el frontend no lo necesita, es superficie XSS innecesaria.
- **⚠️ PlanProtectionMiddleware no usa error format estandarizado**: devuelve `{"detail": "..."}`.

### Recomendación

1. Activar CSRF enforcement (`CSRF_ENABLED=True`) cuando el frontend envíe `X-CSRF-Token`.
2. Pasar `audit_service` al login desde el router — hoy se pierden eventos críticos.
3. Agregar `Content-Security-Policy` header.
4. Evaluar si eliminar `accessToken` del body de login (dejar solo cookie).
5. Implementar rotación de tokens o al menos documentar la limitación.

---

## 4. Seguridad avanzada

**Score: 70/100**  ✅ Mejorado (estimado 45 → 70)

### Lo que se hizo

- **Rate limiting con store interface**: `RateLimitStore` ABC, `SlidingWindowMemoryStore`. Reglas endpoint-specific.
- **Audit log en MongoDB**: `AuditService` con 10 tipos de eventos. Índices para consultas por tenant/evento/actor.
- **Endpoint de auditoría**: `GET /api/admin/audit-logs` con filtros por evento, actor, fechas y paginación.
- **Índices en `audit_logs`**: por `tenantId+timestamp`, `event+timestamp`, `actor_id+timestamp`.

### Lo que quedó pendiente

- **❌ No hay RedisStore implementado**: `SlidingWindowMemoryStore` es la única implementación. No escala horizontalmente. Redis está en `docker-compose.yml` pero no se usa.
- **❌ No hay WAF / Cloudflare**.
- **❌ No hay alertas**: no hay notificaciones para login fallido recurrente, eliminación de tenant, cambios de SUPER_ADMIN.
- **❌ No hay anti-scraping / fingerprinting de clientes**.
- **⚠️ Rate limit rules no cubren todos los endpoints públicos**: cubre login, register, forgot-password, reset-password. Pero no cubre `/api/tenants/plans`, `/api/payments/*`, etc.
- **⚠️ AuditService es opcional en todos lados**: si no se pasa, los eventos se pierden silenciosamente.

### Recomendación

1. Implementar `RedisStore` para rate limiting — la infraestructura ya está en docker-compose.
2. Agregar alertas para eventos críticos (email y/o dashboard).
3. Hacer obligatorio `AuditService` en métodos críticos (login, delete, suspend, approve payment).
4. Considerar Cloudflare delante del backend para WAF y DDoS protection.

---

## 5. Base de datos

**Score: 78/100**  ✅ Mejorado (estimado 60 → 78)

### Lo que se hizo

- **`.to_list(None)` resuelto**: todas las queries tienen límites explícitos (`to_list(limit)`).
- **`TransactionManager`**: context manager con session + fallback con compensación. Usado en register, approve_payment, delete_tenant.
- **Proyecciones agregadas**: queries admin usan `find(query, {field1: 1, ...})` en vez de documentos completos.
- **`re.escape` en búsquedas**: AdminTenantService escapa regex en search.
- **Índices agregados**: para audit_logs (3), tenant payments por fecha, tenants por subscriptionStatus, tenants por subscriptionStatus+subscriptionEndDate.
- **`validate_required_indexes()`**: verificación read-only en startup (no dropea ni crea).
- **`Collections` class**: constantes centralizadas para nombres de colecciones.

### Lo que quedó pendiente

- **⚠️ `MONGODB_TRANSACTIONS_ENABLED=False` por defecto**: Atlas M0 no soporta transacciones (requiere replica set). El TransactionManager tiene fallback, pero el fallback solo corre compensación si hay error — y la compensación no está implementada en los servicios.
- **⚠️ `datetime.utcnow()` naive**: todas las fechas son naive UTC. No rompe nada, pero no es best practice. Mejor usar `datetime.now(timezone.utc)`.
- **⚠️ Sin migraciones versionadas**: `scripts/migrate_indexes.py` y `create_indexes()` en `database.py` no son migraciones formales.
- **⚠️ Acceso `db.tenants` vs `db[Collections.TENANTS]`**: inconsistencia. Algunos lugares usan atributos directos (ej: `db.tenants`), otros usan constantes (ej: `db[Collections.TENANTS]`).

### Recomendación

1. Migrar a `datetime.now(timezone.utc)` en toda la base de código (o al menos en nuevos desarrollos).
2. Evaluar si las transacciones son necesarias ahora o se pueden habilitar con un tier superior de Atlas.
3. Documentar el proceso de migración de índices para producción.
4. Estandarizar acceso a colecciones usando `Collections` constantes.

---

## 6. Rendimiento

**Score: 72/100**  ✅ Mejorado (60 → 72)

### Lo que se hizo

- **GZip compression**: `GZipMiddleware(minimum_size=1000)` en el stack.
- **Dashboard paralelizado**: `AdminTenantService.get_dashboard()` usa `asyncio.gather()` para 9 queries concurrentes.
- **TTL cache**: `TTLCache` con 30s de expiración para dashboard SUPER_ADMIN.
- **Índices de rendimiento**: índices compuestos para queries admin y reportes.
- **Proyecciones**: queries devuelven solo campos necesarios.

### Lo que quedó pendiente

- **❌ Cache solo in-memory**: `TTLCache` no escala horizontalmente. Redis está en docker-compose pero no se usa para caché ni rate limiting.
- **❌ Sin observabilidad**: no hay métricas de latencia por endpoint, no hay tracing, no hay structured logging JSON.
- **⚠️ No hay Redis Pool/CacheService**: el cache actual es singleton en memoria — se pierde al reiniciar, no es compartido entre instancias.
- **⚠️ Rate limit store in-memory**: mismo problema — no escala a multi-instancia.

### Recomendación

1. Implementar `RedisCache` como backend opcional para `TTLCache`, o un `CacheService` con fallback a memoria.
2. Implementar `RedisStore` para rate limiting.
3. Agregar métricas básicas: latencia P50/P95/P99 por endpoint, tasa de error, uso de rate limit.
4. Migrar logs a JSON estructurado para mejor integración con sistemas de logging (Datadog, Grafana Loki, etc.).

---

## 7. DevOps

**Score: 70/100**  ✅ Mejorado (estimado 40 → 70)

### Lo que se hizo

- **Dockerfile multi-stage**: builder + production image con HEALTHCHECK.
- **docker-compose**: MongoDB 7 + Redis 7 + backend, con healthchecks y depends_on condicional.
- **CI/CD GitHub Actions**: lint (ruff + mypy) + test (pytest unit) con MongoDB service container.
- **`/health` endpoint**: verifica API viva.
- **`/ready` endpoint**: verifica conexión MongoDB (retorna 503 si no responde).
- **`.env.example`** presente con defaults seguros.

### Lo que quedó pendiente

- **⚠️ CI solo corre tests unitarios**: `python -m pytest tests/unit/ -v`. Los tests de integración (`test_auth_multi_tenant.py`, `test_security_hardening.py`) no se ejecutan en CI.
- **⚠️ `mypy` errors ignorados**: `|| true` al final — los errores de tipo no rompen el build.
- **❌ No hay security scan ni dependency audit** en CI.
- **❌ No hay build y push de Docker image** en CI.
- **❌ No hay staging environment** antes de producción.
- **❌ No hay backups documentados**: ni script, ni schedule, ni restore test.
- **❌ No hay Sentry / error tracking**.
- **⚠️ Sin structured logging**: logs planos de uvicorn, no JSON.

### Recomendación

1. Agregar tests de integración al CI (con MongoDB service container).
2. Agregar `pip-audit` o `safety` para dependency scanning.
3. Agregar build + push de Docker image a GHCR o Docker Hub.
4. Documentar y automatizar backups de MongoDB Atlas.
5. Integrar Sentry para error tracking en producción.
6. Migrar a logging JSON estructurado.

---

## 8. Calidad del código

**Score: 80/100**  ✅ Mejorado (61 → 80)

### Lo que se hizo

- **7 `get_tenant_from_header_*` unificados**: ahora hay un único `get_tenant_from_request` en `api/dependencies.py`.
- **Routers reducidos**: tenants.py (-75%), admin.py (-60%).
- **Servicios con constructor injection**: todos reciben `db`, testeables.
- **~5200 líneas de tests**: 23 archivos de test cubriendo:
  - Auth multi-tenant (345 líneas)
  - Security hardening (CORS, CSRF, headers, regex escape, error format) (554 líneas)
  - TenantAuthService extraction (483 líneas)
  - Admin service extraction (304 líneas)
  - Audit model/service/integration (768 líneas)
  - Transactions (589 líneas)
  - Rate limiting (321 líneas)
  - Error format & status codes (551 líneas)
  - Calidad de código (84 líneas)
  - Monetización (246 líneas)
  - DevOps (166 líneas)
  - Rendimiento (212 líneas)
- **`check_seed_protected`** en utils protege seed data demo.
- **Uso consistente de Pydantic v2** y `model_dump()` / `model_fields`.

### Lo que quedó pendiente

- **⚠️ `sales.py`**: 609 líneas sin extraer a servicio. Es el router con más lógica de negocio hoy.
- **⚠️ `test_tenant_auth.py` tests frágiles**: varios tests importan `get_tenant_from_header_tenants` que ya no existe (test obsoleto que fallaría).
- **⚠️ Comentarios con encoding**: algunos archivos aún tienen `&#237;` en vez de `í` (tenants.py líneas 295, 309, 314, 342, 378, 413, 448, etc.).
- **⚠️ Inconsistencia en acceso a colecciones**: `db.tenants`, `db[Collections.TENANTS]`, `db["users"]`, `db[Collections.USERS]` — tres estilos diferentes.
- **⚠️ Tests duplican fixtures**: `conftest.py` tiene fixtures session-scoped, pero `test_auth_multi_tenant.py` define sus propias function-scoped para evitar problemas de event loop en Windows.
- **⚠️ `test_tenant_auth.py` línea 44**: importa `get_tenant_from_header_tenants` que fue reemplazado por `get_tenant_from_request` — test fallaría si se ejecuta.

### Recomendación

1. Extraer `SalesService` con toda la lógica de ventas.
2. Revisar y corregir tests que importan funciones eliminadas.
3. Estandarizar acceso a colecciones (usar siempre `Collections` constantes).
4. Limpiar encoding en comentarios.
5. Consolidar fixtures de test (eliminar duplicación conconftest.py y módulos específicos).

---

## 9. Monetización como API comercial

**Score: 68/100**  ✅ Mejorado (estimado 50 → 68)

### Lo que se hizo

- **MockPaymentProvider**: servicio completo con checkout session, verificación, webhook handler.
- **Payment router**: `POST /checkout`, `POST /webhook`, `GET /sessions/{id}`.
- **Flujo de pago completo (mock)**: create → mock-checkout → webhook completion.
- **Pagos por transferencia**: flujo de aprobación/rechazo por SUPER_ADMIN.
- **Plan protection middleware**: bloquea rutas PREMIUM si el tenant no tiene plan PREMIUM.
- **`require_plan` dependency**: factory para proteger endpoints por plan.
- **Demo data**: 2 tenants demo (Basic + Premium) con seed data completa (productos, clientes, ventas, facturas, asistencias).
- **Precios de planes**: BASIC $20/mes, PREMIUM $30/mes.

### Lo que quedó pendiente

- **❌ No hay pasarela de pagos real**: Stripe, MercadoPago, PayPhone, etc.
- **❌ No hay renovación automática**: la suscripción se extiende manualmente.
- **❌ No hay webhooks de pagos reales**.
- **❌ No hay facturación legal/electrónica** (depende del país).
- **❌ No hay términos, privacidad, consentimiento**.
- **⚠️ MockPaymentProvider no persiste en DB**: los datos de sesión están en memoria. Si el servidor reinicia, se pierden.
- **⚠️ PlanProtectionMiddleware no usa error format estandarizado**.
- **⚠️ REGISTRATION_WHITELIST hardcodeado**: `tenants.py` línea 42 tiene `{"dennischapu94@gmail.com"}` hardcodeado. Debería ser configurable.

### Nivel actual

**Senior técnico / Pre-producción. Vendible como beta controlada.**

Como portafolio: **excelente** — tiene lo que un reclutador senior quiere ver (servicios, tests, seguridad, Docker, CI/CD).

Como SaaS real: **beta controlada** — podés venderlo a los primeros 5-10 clientes con supervisión manual, pero necesitás pagos reales y monitoreo antes de escala.

### Recomendación

1. Hacer `REGISTRATION_WHITELIST` configurable vía settings + `.env`.
2. Evaluar integración con Stripe o MercadoPago como primer proveedor real.
3. Persistir datos de sesiones de pago en MongoDB en vez de memoria.

---

## Riesgos críticos actuales

1. **❌ Login sin audit logging**: el router no pasa `audit_service` al `TenantAuthService.login()` — ni logins exitosos ni fallidos se registran. Regresión de la extracción.
2. **⚠️ CSRF no enforced**: el middleware existe pero `CSRF_ENABLED=False`. Producción sin CSRF es riesgoso con cookies HttpOnly.
3. **⚠️ Sin Redis en rate limit ni cache**: docker-compose tiene Redis pero no se usa. Rate limit y cache son in-memory — no sirven en multi-instancia.
4. **⚠️ CI no corre tests de integración**: tests críticos de CORS, CSRF, auth multi-tenant, seguridad no se ejecutan en CI.
5. **⚠️ `sales.py` sin extraer**: 609 líneas, es el router más grande y con lógica más compleja (ventas + facturas + inventario + membresías).
6. **❌ `test_tenant_auth.py` test fallido**: importa `get_tenant_from_header_tenants` que ya no existe.
7. **⚠️ Sin refresh token / revocación de JWT**: 24h de ventana si un token se filtra.

---

## Fortalezas actuales

- **Arquitectura extraída en servicios**: 6 servicios con constructor injection, testables.
- **Routers realmente thin**: tenants.py y admin.py reducidos 60-75%.
- **Dependencias unificadas**: `get_tenant_from_request`, `require_roles`, `require_plan` centralizados.
- **Middleware stack completo**: CORS, CSRF, RateLimit, SecurityHeaders, PlanProtection, CatchAllError, GZip — en el orden correcto.
- **Tests sustanciales**: ~5200 líneas de tests en 23 archivos.
- **Error format estandarizado**: `{error: {code, detail, message}}` con handler global.
- **Transacciones con fallback**: TransactionManager con compensación.
- **CORS cerrado**: sin wildcard, orígenes explícitos.
- **API versioning ready**: routers usan `/api/tenants`, `/api/admin`, etc — fácil agregar `/api/v1/`.
- **Docker + docker-compose + CI/CD**: la base DevOps está.
- **Mock payment flow**: checkout + webhook para demostración.
- **Audit trail**: 10 eventos auditables con endpoint de consulta.
- **Plan protection**: middleware y dependency factory.

---

## Recomendaciones próxima iteración

### Prioridad 1 — Bugs y regresiones

1. **Pasar `audit_service` al login** en `tenants.py:login_tenant()` — los eventos de login se pierden.
2. **Corregir `test_tenant_auth.py`**: remover import de `get_tenant_from_header_tenants`.
3. **Hacer `REGISTRATION_WHITELIST` configurable** — mover a `settings.py`.

### Prioridad 2 — Hardening fino

4. **Activar CSRF enforcement** cuando el frontend esté listo.
5. **Agregar `Content-Security-Policy`** a SecurityHeadersMiddleware.
6. **Eliminar `accessToken` del body de login** (dejar solo cookie) si el frontend no lo necesita.
7. **Implementar RedisStore + RedisCache** — la infraestructura ya está en docker-compose.

### Prioridad 3 — Calidad y tests

8. **Extraer `SalesService`** de `app/routers/sales.py` (609 líneas).
9. **Agregar tests de integración al CI**: `test_auth_multi_tenant.py`, `test_security_hardening.py`.
10. **Estandarizar acceso a colecciones**: usar siempre `Collections` constantes.

### Prioridad 4 — DevOps

11. **Agregar `pip-audit` o `safety`** al CI para dependency scanning.
12. **Agregar build + push de Docker image** al CI.
13. **Documentar backups de MongoDB Atlas**.

### Prioridad 5 — Preparación producción

14. **Evaluar integración con Stripe/MercadoPago** para pagos reales.
15. **Agregar Sentry** para error tracking.
16. **Migrar a `datetime.now(timezone.utc)`** en todo el código.

---

## Scoring detallado

| Categoría | Puntaje 2026-06-08 | Puntaje 2026-06-10 | Diferencia |
|-----------|:------------------:|:------------------:|:----------:|
| Arquitectura | 62 | **82** | +20 |
| Seguridad | 55 | **78** | +23 |
| Escalabilidad | 58 | **72** | +14 |
| Rendimiento | 60 | **72** | +12 |
| Calidad del código | 61 | **80** | +19 |
| Preparación para producción | 52 | **70** | +18 |
| **Global** | **58** | **76** | **+18** |

---

## Scoring por sub-componente (2026-06-10)

| Sub-componente | Score | Estado |
|---------------|:-----:|:------:|
| Arquitectura hexagonal/limpia | 80/100 | ⚠️ Mejorado |
| API REST design | 80/100 | ✅ Resuelto |
| Seguridad perimetral (CORS, Swagger, headers) | 85/100 | ✅ Resuelto |
| Autenticación y autorización | 75/100 | ⚠️ Mejorado |
| Rate limiting | 70/100 | ⚠️ Mejorado |
| CSRF protection | 60/100 | ⚠️ Mejorado (existe pero no enforced) |
| Auditoría y trazabilidad | 75/100 | ✅ Resuelto |
| Transacciones y consistencia | 65/100 | ⚠️ Mejorado |
| Índices y proyecciones | 80/100 | ✅ Resuelto |
| Caché y rendimiento | 55/100 | ⚠️ Mejorado |
| DevOps y CI/CD | 70/100 | ✅ Resuelto |
| Tests y cobertura | 75/100 | ✅ Resuelto |
| Calidad de código | 80/100 | ✅ Resuelto |
| Monetización y pagos | 60/100 | ⚠️ Mejorado |

---

*Auditoría generada el 2026-06-10. Basada en revisión estática del código en `C:\Users\Dennis\Documents\proyectos-codex\gym-management\gym-backend\`.*
