# Plan de cierre — Backend para producción real

Basado en: `REVISION_PRODUCCION_BACKEND_2026-05-18.md`
Fecha: 2026-05-18
Alcance: backend FastAPI en `gym-management/backend`

## Reglas obligatorias

- No ejecutar build.
- No commitear `.env`.
- No cambiar URLs a producción todavía.
- No migrar a MongoDB Atlas todavía.
- No configurar CORS final todavía.
- Usar commits convencionales.
- No agregar atribución AI ni `Co-Authored-By`.
- Verificar con lectura de código antes de afirmar que algo está listo.

---

## Orden de ejecución (de más crítico a más rápido)

### 1. `.env` fuera de Git

**Problema:** `backend/.env` está trackeado por Git. No debe estar versionado.

**Acción:**
```bash
git rm --cached .env
```
Confirmar que `.gitignore` ya tiene `.env`. Hacer commit.

⚠️ **Pendiente tuyo:** si el JWT secret real alguna vez estuvo en el repo, rotar la clave en `.env`.

---

### 2. Login exija `businessCode` para cuentas reales

**Archivo:** `backend/app/routers/tenants.py` — `login_tenant()`

**Problema:** si no se resuelve `businessCode`, sigue buscando por `username` global.

**Acción:**
- Si NO viene `businessCode` ni `tenantId`:
  - Solo permitir si el tenant encontrado tiene `isDemo=True`.
  - Para cuentas reales: devolver error genérico "Credenciales incorrectas".
- Si viene `businessCode`, resolver tenantId desde ahí como ya se hace.
- Para demos (`isDemo=True`), mantener el comportamiento actual (username + password).

**Relación con frontend:** el frontend review pide:
- No enviar `tenantId` viejo si se manda `businessCode` (punto 3 frontend).
- Hacer `businessCode` requerido en login real (punto 4 frontend).

El backend debe soportar ambos casos: que el frontend envíe `businessCode` o `tenantId`.

---

### 3. Fallback legacy (tenant.password) solo para demo

**Archivo:** `backend/app/routers/tenants.py` — `login_tenant()`

**Problema:** el bloque de backward compatibility (busca tenant por email, valida `tenant.password`) se ejecuta para cualquier tenant.

**Acción:**
- Envolver el bloque legacy con:
```python
if tenant.get("isDemo"):
    # backward compatibility para demos antiguos
```
- Documentar como bloque de migración temporal a eliminar.

---

### 4. `/api/auth/login` legacy deshabilitado o scopeado

**Archivo:** `backend/app/auth/router.py`

**Problema:** existe una ruta `/api/auth/login` que hace login sin tenant scope.

**Acción:**
- Opción A (recomendada): deshabilitar la ruta levantando HTTPException con mensaje "Usar /api/tenants/login".
- Opción B: redirigir a `/api/tenants/login`.
- Documentar que el único endpoint de login es `/api/tenants/login`.

---

### 5. Forgot-password scoped obligatoriamente por tenant

**Archivo:** `backend/app/routers/tenants.py` — `forgot_password()`

**Problema:** si no viene `businessCode` ni `tenantId`, busca solo por username.

**Acción:**
- Exigir `businessCode` o `tenantId`.
- Si no viene ninguno, devolver mensaje genérico y NO procesar reset.
- Para demos, mantener compatibilidad actual.

---

### 6. Startup fail-fast

**Archivo:** `backend/app/main.py` — `lifespan()`

**Problema:** captura excepciones, imprime traceback y sigue. La API puede quedar "levantada" aunque falle MongoDB.

**Acción:**
- Si falla conexión a MongoDB: hacer `raise` y que la app no arranque.
- Si fallan índices críticos: loggear error grave y hacer `raise`.
- Reemplazar `print()`/`traceback.print_exc()` con logging estructurado (`logger.error()`).
- Usar `sys.exit(1)` o dejar que la excepción bubble up.

---

### 7. Índices fuera del startup

**Archivo:** `backend/app/database.py` + `backend/app/main.py`

**Problema:** `create_indexes()` puede hacer `drop_index()` en startup.

**Acción:**
- Crear script separado: `backend/scripts/migrate_indexes.py`
  - Usar la misma lógica de `create_indexes()` pero como CLI ejecutable.
  - Documentar que debe correrse manualmente antes de deploy.
- En `main.py` → `lifespan()`:
  - Eliminar la llamada a `create_indexes()`.
  - Opcional: validación ligera de que los índices existen (solo lectura, sin crear/dropear).
- Actualizar documentación en `database.py` y `config.py`.

---

### 8. Tests backend de seguridad multi-tenant

**Archivo:** `backend/tests/`

**Problema:** no hay tests backend propios.

**Acción mínima:**
- Test: login multi-tenant con dos tenants usando mismo email → debe funcionar si cada uno usa su `businessCode`.
- Test: `businessCode` único → registrar dos tenants con mismo nombre → segundo debe tener sufijo.
- Test: login sin `businessCode` para cuenta real → debe fallar.
- Test: reset password scopeado por tenant.
- Test: aislamiento CRUD — un tenant no puede ver datos de otro.
- Test: fallback legacy solo funciona para demos.
- Test: `/api/auth/login` legacy devuelve error.

Usar pytest + httpx. Base de datos de test separada o MongoDB en memoria.

---

## Pendientes que NO cubre este plan (decisión tuya o de infra)

| Punto | Motivo |
|-------|--------|
| Rotar JWT_SECRET si estuvo en Git | Depende de si hubo exposición real |
| Rate limit con Redis | Necesita servidor Redis — infraestructura |
| Email real (forgot-password) | Necesita SendGrid/Resend/Mailgun + API keys |
| Migrar JWT a cookies HttpOnly | Cambio de modelo de auth — decisión arquitectónica |
| CORS final, URLs públicas, Atlas | Ya documentado como pendiente en `config.py` |

---

## Relación con frontend

Los cambios de backend habilitan que el frontend:

1. **Login requiera `businessCode`**: el backend ya no acepta login global para cuentas reales, así que el frontend puede quitar el "(opcional)" y marcarlo como requerido.
2. **No enviar `tenantId` viejo**: el backend prioriza `businessCode` sobre `tenantId`, pero igual conviene que el frontend no mande ambos (ver punto 3 de frontend review).
3. **ConfigPage como fuente real**: el backend ya expone `GET /api/tenants/me` con todos los datos del negocio (incluyendo `businessCode`). El frontend review pide migrar la edición de datos a endpoints reales — el backend tiene `PUT /api/tenants/me` listo para eso.

---

## Checklist de ejecución

- [ ] 1. `git rm --cached .env` + commit
- [ ] 2. Login exige `businessCode` (excepto demo)
- [ ] 3. Fallback legacy solo demo
- [ ] 4. `/api/auth/login` deshabilitado
- [ ] 5. Forgot-password scoped obligatorio
- [ ] 6. Startup fail-fast
- [ ] 7. Índices → script separado
- [ ] 8. Tests backend

## Veredicto esperado después de ejecución

```txt
STATUS: listo para preproducción técnica, pendiente infraestructura
```
