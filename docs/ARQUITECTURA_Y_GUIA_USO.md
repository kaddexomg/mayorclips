# Guía Operativa Integral — MayorClips

MayorClips es tu plataforma soberana de **clipping inteligente con IA, edición de videos verticales y publicación multi-red**, diseñada con la identidad visual moderna de **Quanty Clips** (tema `#060B10` y acento `#2BF0C8`) y optimizada específicamente para tu laptop Ryzen 5.

---

## 1. Inicio Rápido (En 1 Clic)

Simplemente haz doble clic sobre el archivo raíz:
```
INICIAR-MAYORCLIPS.bat
```
Este script:
1. Arranca el servidor Backend FastAPI en segundo plano (`http://127.0.0.1:8000`).
2. Arranca la interfaz web en Vite React (`http://127.0.0.1:5173`).
3. Abre automáticamente tu navegador en la pantalla principal.

---

## 2. Los Tres Módulos del Sistema

### A. Clipper IA (Audio-First)
1. Ve a la pestaña **Nuevo Proyecto**.
2. Pega el link de cualquier transmisión o video de **Twitch, Kick o YouTube**.
3. El sistema activa la ingesta **Audio-First**: solo descarga los primeros 50-100 MB de audio en vez de descargar 4 GB de video en 1080p, preservando tu disco y la memoria RAM de tu procesador Ryzen 5.
4. **El Pulpo IA** (con el pool de tus 7 llaves de Gemini) analiza los picos de risas, chat y volumen, encontrando entre 5 y 12 momentos virales candidatos con puntuación de retención (ej: 96% Viral).
5. En la pestaña **Clips Virales**, puedes:
   - Ver el texto gancho (hook) y el comentario de evento (sticker flotante).
   - Abrir el **Personalizador** para cambiar el layout:
     - `Split Screen`: Streamer arriba (35%) + Videojuego abajo (65%).
     - `Centrado`: Recorte inteligente al centro.
     - `Fondo Desenfoque`: Video 16:9 nítido en el centro con fondo 9:16 borroso dinámico.
   - Elegir el estilo de subtítulos: `Alex Hormozi`, `Neón Quanty`, `Karaoke`, `MrBeast` o `Minimal`.
   - Presionar **Renderizar 9:16**: utiliza la aceleración de hardware por GPU integrada **AMD AMF** (`h264_amf`), codificando clips de 60 segundos en tiempo récord (~1 a 2 minutos).

---

### B. Publicador Multi-Red Soberano
1. Al tener un clip listo, pulsa el botón **Publicar** (ícono de compartir).
2. Se abre el compositor multi-red:
   - **Instagram Reels**: Se publica en tu cuenta profesional/creador mediante la Graph API oficial.
   - **Facebook Reels**: Se publica en tu página de Facebook de forma pública.
   - **TikTok (Modo 1-Tap Público)**: Se envía directamente a la bandeja de creador de tu app TikTok. Te llega una notificación al teléfono, abres la app y tocas "Publicar": el video sale **100% público** sin sufrir los bloqueos de privacidad de las cuentas en desarrollo.
3. Puedes usar el botón **"Optimizar con El Pulpo IA"** para que Gemini redacte copys específicos con los mejores hashtags de tendencia para cada red.

---

### C. Estudio Motion Graphics (Fase 2)
1. Ve a la pestaña **Estudio MG**.
2. Escribe cualquier tema o curiosidad (ej: *"¿Por qué los aviones no vuelan sobre la casa de Messi?"*).
3. Elige el estilo (`Curiosidades`, `Top 5`, `Historia`, `Gráficas`).
4. Pulsa **Generar Video Motion Graphics**: El Pulpo IA redacta el guion, genera la voz en off neuronal gratuita con `edge-tts` (sin gastar APIs) y programa las escenas para componer con **HyperFrames** en código HTML/GSAP.

---

## 3. Estado del Pulpo IA & Llaves Gemini

En la pestaña **El Pulpo IA** tienes la telemetría en vivo:
- **7 API Keys** rotando automáticamente.
- Si una clave alcanza el límite temporal (error 429), el Pulpo conmuta a la siguiente clave en menos de 50 milisegundos y pone la anterior en enfriamiento.
- Si hay congestión en Google, el Pulpo baja al modelo `gemini-3.1-flash-lite`.
- Las respuestas y prompts procesados se guardan en la caché de `storage/cache/`: un clip o tema ya analizado **nunca vuelve a gastar tokens de tu cuota**.

---

## 4. Despliegue en el VPS de JJ Paper (Opcional para 24/7)

En la carpeta `deploy/vps/` cuentas con:
- `setup-vps-db.sql`: Crea la base de datos `mayorclips_db` en el PostgreSQL de tu VPS (`166.0.112.247`), totalmente aislada del ERP MixNet de JJ Paper.
- `mayorclips-publisher.service`: Demonio para systemd con límites estrictos de seguridad (`MemoryMax=400M`) para no interferir con la operación comercial.
- `nginx-mayorclips.conf`: Configuración SSL HTTPS para recibir los callbacks de OAuth.
