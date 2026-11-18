# Contexto TikTok — pausa y punto de retorno

**Fecha:** 18 de noviembre de 2026
**Objetivo:** conectar la cuenta de TikTok a MayorClips para probar la subida de clips.

---

## Dónde quedamos

El código de MayorClips ya está preparado para el flujo correcto, pero **la app de TikTok todavía no se puede guardar** porque el formulario del portal devuelve 4 errores al pulsar *Apply changes*.

Los errores son casi seguro:

1. Icono de app vacío o que no es 1024 × 1024.
2. Descripción vacía.
3. Website URL sin verificar.
4. Privacy / Terms URL sin verificar.

Las URLs **sí existen y funcionan**; TikTok no pide inventarlas, pide **verificarlas**.

---

## Páginas legales ya publicadas (GitHub Pages)

| Página | URL |
|---|---|
| Inicio | https://kaddexomg.github.io/mayorclips/ |
| Privacidad | https://kaddexomg.github.io/mayorclips/privacy.html |
| Términos | https://kaddexomg.github.io/mayorclips/terms.html |

- Publicadas desde `master` / carpeta `/docs`.
- Verificadas con HTTP 200 el 18/11/2026.
- Commit: `1163881 docs(tiktok): paginas legales...`

Si TikTok rechaza `github.io` incluso después de verificar, el plan B es un dominio propio o montar las páginas en el VPS.

---

## Lo que ya se corrigió en el código

| Archivo | Cambio |
|---|---|
| `backend/app/main.py` | PKCE (`code_challenge` S256 + `code_verifier`) automático cuando el redirect es `localhost`/`127.0.0.1`. Sin esto, el login Desktop falla siempre. |
| `publisher/uploaders/tiktok.py` | Chunking correcto (bloques de 64 MB, último hasta 128 MB), `Content-Length`, lectura por chunks en vez de cargar todo en RAM. |
| `publisher/uploaders/tiktok.py` | `exchange_code()` acepta `code_verifier` y lo envía al token endpoint. |

Comprobado: sintaxis Python OK y simulación de chunks de 4 MB a 4 GB cubriendo el archivo completo.
**Aún no se ha probado contra TikTok real.**

---

## Configuración que debe llevar la app en TikTok

| Campo | Valor |
|---|---|
| App name | `MayorClips` |
| Category | *Video editing* o *Utilities* |
| Description | `Herramienta para creadores que analiza transmisiones largas, genera clips verticales y los envía a la bandeja de entrada de TikTok para revisarlos y publicarlos.` |
| Icon | PNG/JPG **1024 × 1024**, máx. 5 MB |
| Platform | **Desktop** |
| Redirect URI | `http://127.0.0.1:8000/oauth/tiktok/callback` |
| Products | **Login Kit** + **Content Posting API** en modo **Upload** |
| Scopes | `user.info.basic`, `video.upload` |

El `Client Key` y el `Client Secret` se copian del portal (estando en **Sandbox**) a:

**MayorClips → Cuentas → Bóveda Central de Credenciales OAuth → Guardar.**

`Apply changes` = guardar. **No** es "enviar a revisión". No pulsar **Submit for review** todavía.

---

## Cómo retomar (checklist)

1. Abrir https://developers.tiktok.com/apps y entrar a la app ya creada (no crear otra).
2. Cambiar el interruptor superior a **Sandbox** (o crear uno con *Create Sandbox*).
3. Rellenar App details con los valores de la tabla de arriba, incluido el icono.
4. Pulsar **Apply changes**.
   - En Sandbox no se verifican las URLs de privacidad/términos.
   - Si aun así bloquea, ir a **URL properties → Verify properties → URL prefix** y usar
     `https://kaddexomg.github.io/mayorclips/`. TikTok entrega un archivo de firma que hay que
     publicar en esa ruta antes de verificar.
5. Copiar **Client Key** y **Client Secret** del sandbox.
6. Pegarlos en MayorClips → Cuentas → Bóveda → Guardar.
7. Pulsar **Iniciar sesión con TikTok** y autorizar con la cuenta agregada como *target user*.
8. Probar la subida de un clip.

### Si el formulario vuelve a fallar

Pedir/guardar:

- El **texto exacto de los 4 errores**, o
- El **archivo de firma** que genera TikTok en URL properties.

Con eso se resuelve en un paso.

---

## Pendientes / avisos

- [ ] Generar o elegir el icono 1024 × 1024.
- [ ] Confirmar si la app ya tiene plataforma **Desktop** y el redirect registrado.
- [ ] Confirmar que el producto es **Upload** (`video.upload`) y no **Direct Post** (`video.publish`).
- [ ] Agregar la cuenta de TikTok como *target user* del sandbox (puede tardar hasta 1 h).
- [ ] Probar el flujo completo.

**Límites reales de TikTok:**

- Sandbox no ofrece Content Posting para videos públicos: el clip puede quedar privado hasta pasar auditoría.
- Máximo 5 videos pendientes por usuario cada 24 h.
- Máximo 6 peticiones por minuto por `access_token`.
- El `access_token` dura ~24 h; el `refresh_token` lo renueva.
- Para producción, TikTok exige una web que parezca un producto real (no una landing simple) y una auditoría con video demo.

---

## Archivos de referencia

- `docs/TIKTOK_SETUP.md` — guía completa del portal y errores típicos.
- `docs/privacy.html`, `docs/terms.html`, `docs/index.html` — páginas publicadas.
- `backend/app/main.py` — OAuth TikTok + PKCE.
- `publisher/uploaders/tiktok.py` — subida a la bandeja + chunking.
