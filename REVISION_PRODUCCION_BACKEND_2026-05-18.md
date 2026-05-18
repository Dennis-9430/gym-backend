# Revisión para producción — Backend

Fecha: 2026-05-18  
Alcance: backend FastAPI en `gym-management/backend`.  
Excluido por pedido: cambio de host público, URL pública, CORS final y cambio de base de datos local a Atlas/producción.

## Veredicto

El backend ya tiene una base multi-tenant bastante mejor: usa `tenantId`, `businessCode`, índices por tenant, middleware de plan y flags para demo/seed. Pero todavía NO lo subiría como producción real sin corregir los puntos críticos de seguridad y operación.

Para portfolio/demo controlada puede servir. Para clientes reales, faltan cierres importantes.

## Estado encontrado

- Últimos commits relevantes:
  - `c7d8eb` — bootstrap flags y pendientes producción.
  - `90e450` — `businessCode` para tenants.
  - `6908cd` — índice compuesto `(tenantId, username)`.
- Working tree backend:
  - `.gitignore` modificado.
- Hallazgo crítico:
  - `.env` está TRACKED por Git según `git ls-files`; aunque `.gitignore` lo tenga, ya quedó dentro del repo.

## Bloqueadores críticos antes de producción real

### 1. `.env` trackeado en backend

**Problema:** `backend/.env` aparece en archivos versionados. Esto es grave: variables locales/secrets no deben existir en Git.

**Ajuste recomendado:**

```bash
git rm --cached .env
```

Luego confirmar que `.env.example` sea el único archivo de ejemplo versionado. Si el JWT secret real alguna vez estuvo en Git, rotarlo.

---

### 2. Login todavía puede caer en búsqueda global

`/api/tenants/login` resuelve `tenantId` desde `businessCode`, pero si no se resuelve, sigue buscando por `username` global.

**Riesgo:** si dos negocios tienen el mismo email/username, el login puede ser ambiguo.

**Ajuste recomendado:**

- Para cuentas reales, exigir `businessCode` o `tenantId`.
- Si `businessCode` no existe, devolver credenciales incorrectas genéricas.
- No hacer búsqueda global por username para usuarios reales.

---

### 3. Fallback legacy por tenant password no está suficientemente cerrado

Si no encuentra usuario en `users`, el login busca tenant por email y valida `tenant.password`.

**Riesgo:** esa compatibilidad debería existir solo para tenants demo o migración controlada.

**Ajuste recomendado:**

- Permitir fallback legacy solo si `tenant.isDemo === true`.
- Documentar y planificar eliminación del campo `tenants.password`.

---

### 4. `/api/auth/login` legacy sigue activo sin tenant scope

El frontend usa `/api/tenants/login`, pero `/api/auth/login` sigue disponible y llama `authenticate_user()` sin tenant.

**Riesgo:** es otra puerta de login global.

**Ajuste recomendado:**

- Deshabilitarlo para producción, o
- requerir tenant scope también ahí, o
- limitarlo a uso interno/demo muy explícito.

---

### 5. Forgot/reset password todavía no está listo para producción

`forgot_password()` resuelve `businessCode`, pero si no viene scope puede buscar solo por username. Además el envío real de email sigue pendiente.

**Ajuste recomendado:**

- Exigir `businessCode` o `tenantId`.
- No procesar reset si no hay tenant resuelto.
- Enviar email real; nunca devolver tokens.
- Guardar tokens/nonce hasheados o implementar invalidación/reuso único.
- Aplicar rate limit específico.

---

### 6. Rate limit en memoria e insuficiente para auth

Existe `RateLimitMiddleware`, pero:

- usa memoria local;
- no sirve en múltiples instancias;
- `LOGIN_RATE_LIMIT = 10` existe pero no se aplica diferenciado.

**Ajuste recomendado:**

- Usar Redis o store compartido.
- Aplicar límites específicos a login, forgot-password y register.
- Considerar bloqueo temporal por usuario+tenant+IP.

---

### 7. Startup no debe esconder errores críticos

En `main.py`, el `lifespan()` captura excepciones, imprime traceback y continúa.

**Riesgo:** la API puede quedar “levantada” aunque MongoDB, índices o seeds fallen.

**Ajuste recomendado:**

- En producción, fallar rápido si falla conexión DB o índices críticos.
- Usar logging estructurado, no `print()`/`traceback.print_exc()`.

---

### 8. Índices se crean/modifican en startup

`create_indexes()` puede hacer `drop_index()` ante conflictos. Ya está documentado como pendiente, pero para producción sigue siendo bloqueante.

**Ajuste recomendado:**

- Extraer migraciones de índices a script controlado.
- No dropear índices automáticamente al iniciar la app.
- Mantener startup solo con validación ligera.

> Esto no cambia el host ni la BD local; es preparación de seguridad operativa.

---

### 9. Falta suite de tests backend propia

No encontré tests backend propios fuera de `venv`/paquetes.

**Ajuste recomendado mínimo:**

- Tests de login multi-tenant con dos tenants usando mismo email.
- Tests de `businessCode` único.
- Tests de reset password scopeado por tenant.
- Tests de aislamiento CRUD por tenant.
- Tests de permisos por rol/plan.

## Pendientes altos

- Centralizar extracción de tenant/JWT en una dependencia común; hoy hay lógica duplicada en routers.
- Revisar políticas de contraseña: mínimo 6 es bajo para producción real.
- Implementar refresh/revocación o migrar a cookies HttpOnly si se decide ese modelo.
- Ocultar `/docs`/`openapi.json` en producción o protegerlos.
- Revisar roles por endpoint; hay controles, pero no están totalmente centralizados.
- Facturas/email/pagos todavía son funcionalidad incompleta para producción comercial.
- Agregar `.venv/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/` al `.gitignore` backend.

## Checklist mínimo antes de deploy real

- [ ] Sacar `.env` del tracking de Git.
- [ ] Rotar secretos si estuvieron versionados.
- [ ] Cerrar login real para exigir `businessCode`/tenant.
- [ ] Restringir fallback legacy solo a demo.
- [ ] Deshabilitar o scopear `/api/auth/login`.
- [ ] Scopear forgot-password obligatoriamente por tenant.
- [ ] Implementar rate limit real para auth.
- [ ] Hacer startup fail-fast ante errores críticos.
- [ ] Sacar migración de índices del startup.
- [ ] Crear tests backend mínimos de seguridad multi-tenant.

## Conclusión

Backend: **no listo para producción real todavía**. Está cerca para demo/portfolio, pero para subir con usuarios reales primero hay que cerrar `.env`, login global, reset password, rate limit, startup e índices.
