# Conexión de TikTok con MayorClips — guía definitiva

## 1. Qué API necesita MayorClips (y cuál NO)

MayorClips usa **dos productos** de TikTok for Developers, no uno:

| Producto | Para qué | Scope |
|---|---|---|
| **Login Kit** | Que el creador autorice la app y la app reciba un `access_token` | `user.info.basic` |
| **Content Posting API → Upload** | Subir el MP4 a la **bandeja de entrada** del creador | `video.upload` |

El endpoint que ya implementa el proyecto es:

```
POST https://open.tiktokapis.com/v2/post/publish/inbox/video/init/
```

Ese endpoint **no publica solo**: deja el video como borrador en la bandeja de TikTok. Al creador le llega
una notificación al móvil, abre la app, revisa el clip y pulsa **Publicar**. Ese es el modo "1-Tap" del que
habla el README.

### La confusión típica

TikTok tiene **dos modos** dentro de la misma Content Posting API:

| Modo | Endpoint | Scope | Publica solo | Requiere auditoría |
|---|---|---|---|---|
| **Direct Post** | `/v2/post/publish/video/init/` | `video.publish` | Sí | Sí, obligatoria |
| **Upload (bandeja)** | `/v2/post/publish/inbox/video/init/` | `video.upload` | No, el creador confirma | También, para que el contenido sea público |

Si en el portal activaste **Direct Post** (`video.publish`), estás configurando el modo equivocado.
MayorClips necesita **Content Posting API con la opción Upload**, y el scope **`video.upload`**.

> Si tu app solo tiene `video.publish`, el backend responderá `scope_not_authorized` al intentar subir a la bandeja.

---

## 2. Qué significan los campos que te pide el formulario

En **App details** TikTok pide:

| Campo | Qué poner en MayorClips |
|---|---|
| **App name** | `MayorClips` |
| **App icon** | PNG/JPG cuadrado de 1024 × 1024 px, máx. 5 MB |
| **Category** | La más cercana: *Video editing* / *Utilities* / *Productivity* |
| **Description** | "Herramienta local para crear clips verticales y subirlos a la bandeja de creador de TikTok." |
| **Platforms** | **Desktop** (recomendado para probar en tu PC) |
| **Website URL** | `https://kaddexomg.github.io/mayorclips/` |
| **Privacy Policy URL** | `https://kaddexomg.github.io/mayorclips/privacy.html` |
| **Terms of Service URL** | `https://kaddexomg.github.io/mayorclips/terms.html` |

Esas tres URLs ya están creadas en la carpeta `docs/` de este repositorio. Para que existan públicamente:

1. Sube los archivos a GitHub (`git add docs && git commit && git push`).
2. En GitHub: **Settings → Pages → Source: Deploy from a branch → Branch: `master` / folder: `/docs` → Save**.
3. Espera 1–2 minutos y abre `https://kaddexomg.github.io/mayorclips/`.

Si algún día tienes dominio propio (por ejemplo `mayorclips.com`), solo cambias esas tres URLs.

**No inventes URLs que no existan**: TikTok revisa que respondan. En **Sandbox** no hace falta verificar
esas URLs (solo se verifica la URL de Content Posting si usas `PULL_FROM_URL`, que MayorClips no usa).
En **Producción** sí hay que verificarlas con el botón **URL properties**.

---

## 3. Desktop vs Web: la decisión que te bloquea

TikTok impone reglas distintas según la plataforma que marques:

| | **Desktop** | **Web** |
|---|---|---|
| Redirect URI | Solo `http://localhost:PUERTO/...` o `http://127.0.0.1:PUERTO/...` | Solo `https://...` público |
| PKCE | **Obligatorio** (`code_challenge` S256 + `code_verifier`) | No obligatorio |
| Sirve para probar en tu PC | **Sí** | No (necesitas dominio HTTPS público) |

MayorClips corre en tu PC (`http://127.0.0.1:8000`), así que la opción correcta hoy es **Desktop**:

```
http://127.0.0.1:8000/oauth/tiktok/callback
```

Ese valor ya es el que muestra la Bóveda de Credenciales de la app. El backend convierte el placeholder
`.local` del `.env` en `http://127.0.0.1:8000`.

> **Cambio ya aplicado en el código:** el backend ahora genera PKCE automáticamente cuando el redirect es
> `localhost`/`127.0.0.1`. Sin eso, el login de TikTok en modo Desktop fallaba siempre.

Si en el portal ya marcaste **Web**, tienes dos caminos:

- Añadir también **Desktop** y registrar el callback local (recomendado para probar ya).
- O desplegar el backend en un dominio HTTPS real y usar Web (`https://tudominio/oauth/tiktok/callback`).

---

## 4. Paso a paso en TikTok for Developers

1. Entra en <https://developers.tiktok.com/> con tu cuenta.
2. **Manage apps → Connect an app**. Elige tu organización o tu cuenta personal.
3. **App details**:
   - Rellena nombre, icono, categoría y descripción.
   - Añade la plataforma **Desktop**.
   - Pega las tres URLs de GitHub Pages.
   - Guarda.
4. **Products → Add products**:
   - **Login Kit**.
   - **Content Posting API**. Dentro de su configuración elige **Upload** (no Direct Post).
5. En **Login Kit**, añade el redirect URI:
   ```
   http://127.0.0.1:8000/oauth/tiktok/callback
   ```
   Debe ser idéntico, sin barra final extra.
6. En **Scopes**, asegúrate de tener:
   ```
   user.info.basic
   video.upload
   ```
7. Pasa el toggle superior a **Sandbox** y crea un sandbox (por ejemplo `dev-local`).
   - En **Sandbox settings → Target users → Add account**, inicia sesión con la cuenta de TikTok
     que vas a usar para probar (máximo 10 cuentas). Puede tardar hasta una hora en aparecer.
   - Copia el **Client Key** y **Client Secret** que se muestran **en modo Sandbox**.
8. Abre MayorClips → pestaña **Cuentas** → **Bóveda Central de Credenciales** → pega `Client Key` y
   `Client Secret` → **Guardar**.
9. Pulsa **Iniciar sesión con TikTok**, autoriza con tu cuenta y vuelve a la app.
10. Renderiza o elige un clip y publícalo. Debe aparecer en tu bandeja de creador de TikTok.

> **Importante:** el `Client Secret` no se inventa ni se configura en TikTok. TikTok te lo genera y tú lo
> copias a MayorClips. Es la "clave secreta" que te pedía la app.

---

## 5. Sandbox: qué esperar

- En Sandbox puedes probar Login Kit y el flujo de subida **sin enviar la app a revisión**.
- TikTok advierte que **Sandbox no ofrece Content Posting para videos públicos**. Es probable que el video
  quede privado o que la publicación pública no esté disponible hasta pasar la auditoría.
- Límites reales de la API:
  - Máximo **5 videos pendientes** por usuario cada 24 h.
  - Máximo **6 peticiones por minuto** por `access_token`.
  - `access_token` dura ~24 h; el `refresh_token` permite renovarlo.
- Cuando confirmes que el flujo funciona, solicita la **auditoría de Content Posting API** desde el portal.
  La revisión puede tardar de varios días a dos semanas y suele pedir un **video demo** del flujo completo.

---

## 6. Problemas que ya quedaron corregidos en el código

| Problema | Síntoma | Estado |
|---|---|---|
| Faltaba PKCE en modo Desktop | TikTok devolvía error al canjear el `code` | Corregido en `backend/app/main.py` |
| `chunk_size = tamaño total` siempre | Videos de más de 64 MB eran rechazados | Corregido en `publisher/uploaders/tiktok.py` |
| Faltaba `Content-Length` en el PUT | Subidas grandes podían fallar | Corregido |
| El video se cargaba entero en RAM | Picos de memoria en clips grandes | Ahora se lee por chunks |

---

## 7. Errores frecuentes y qué significan

| Error de TikTok | Causa probable |
|---|---|
| `scope_not_authorized` | La app no tiene `video.upload` aprobado/autorizado |
| `access_token_invalid` | Token caducado (24 h) o credenciales de otro sandbox |
| `spam_risk_too_many_pending_share` | Más de 5 videos pendientes en 24 h; publica o descarta los anteriores |
| `url_ownership_unverified` | Usaste `PULL_FROM_URL` sin verificar dominio; MayorClips usa `FILE_UPLOAD` |
| `invalid_request` en el login | El redirect URI no coincide exactamente con el registrado |
| `10007` / error de plataforma | Marcaste Desktop pero usaste un redirect HTTPS público, o al revés |

---

## 8. Resumen en una línea

Necesitas **Login Kit + Content Posting API en modo Upload (`video.upload`)**, con la app configurada como
**Desktop**, redirect `http://127.0.0.1:8000/oauth/tiktok/callback`, y las URLs de privacidad/términos
publicadas (GitHub Pages). El código de MayorClips ya está listo para ese flujo.
