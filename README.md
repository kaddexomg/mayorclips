# 🎬 MayorClips

> **Plataforma Soberana de Clipping Inteligente con IA, Edición Vertical 9:16, Movimientos Cinematográficos y Publicador Multi-Red.**

MayorClips está inspirado en la identidad visual de alto rendimiento de **Quanty Clips** (`#060B10` y `#2BF0C8`), diseñado con las directrices de ingeniería de diseño de **Emil Kowalski** (feedback táctil, curvas de resorte) y **Apple Design** (interfaces fluidas, profundidad y glassmorphism).

---

## 🚀 Características Principales

### 1. Ingesta de Streams Largos (8 a 10 Horas)
* **Heatmap & Retention Hunting:** Para directos masivos de 8 a 10 horas en Twitch, Kick o YouTube, MayorClips analiza la **curva de retención y repetición de la audiencia (heatmap)** y la densidad del chat sin necesidad de descargar gigabytes de video.
* **Pipeline Audio-First:** Descarga quirúrgicamente solo los tramos de audio clave (~15 MB) alrededor de los momentos de risas, gritos o picos virales.
* **Cero Colapso de RAM:** Optimizado para correr con fluidez en procesadores como el AMD Ryzen 5 sin saturar la memoria del equipo.

### 2. El Pulpo IA (Router Multi-API con 7 Keys de Gemini)
* **Pool Dinámico de 7 API Keys:** Rotación automática ante errores de cuota (HTTP 429) en menos de 50 milisegundos.
* **Modelos Authorizados:** `gemini-3-flash-preview` y `gemini-3.1-flash-lite`.
* **Caché Inteligente SHA-256:** Ningún análisis ni transcripción repetida vuelve a consumir cuota diaria.
* **Voz Neuronal Gratuita:** Síntesis de voz con `edge-tts` y marcas de tiempo por palabra con precisión de milisegundos.

### 3. Motor de Render Acelerado por Hardware
* **Aceleración AMD AMF:** Codificación acelerada por hardware (`h264_amf`) que procesa clips verticales en tiempo récord (~1-2 minutos por clip).
* **3 Layouts de Cámara:**
  * `Split Screen`: Cámara del streamer arriba (35%) + Gameplay abajo (65%).
  * `Centrado Inteligente`: Recorte vertical 9:16 enfocado.
  * `Fondo Desenfoque`: Video 16:9 centrado con fondo desenfocado dinámico.
* **5 Estilos de Subtítulos Animados:**
  * *Alex Hormozi* (Cyan Bold con borde negro).
  * *Neón Quanty* (`#2BF0C8` brillante).
  * *Karaoke Progresivo* (Llenado dinámico palabra a palabra).
  * *MrBeast Pop-Up* (Amarillo oro de alto impacto).
  * *Minimal Blanco* (Elegante y limpio).

### 4. Cámara IA & Compatibilidad Higgsfield MCP
* **Estudio de B-Roll Cinematográfico:** Genera tomas con trayectorias de cámara:
  * `Zoom In (Dolly In)`
  * `Zoom Out (Reveal)`
  * `Pan Derecha / Izquierda`
  * `Órbita 3D`
* **Arquitectura Dual:**
  * *Modo Open Alternative:* Generación cloud sin costo ni uso de VRAM local.
  * *Higgsfield Ready:* Conector compatible con el MCP oficial (`higgsfield-mcp-unified`). Basta con ingresar tu API Key para activar modelos de cine 4K.

### 5. Publicador Multi-Red Soberano & Estadísticas Reales
* **Instagram Reels:** Publicación directa en público mediante Meta Graph API oficial.
* **Facebook Reels:** Publicación en páginas oficiales de creador.
* **TikTok (Modo 1-Tap Público):** Envío directo a la bandeja de entrada de tu app de TikTok. Llega la notificación a tu móvil, pulsas "Publicar" y sale **100% público** sin sufrir los bloqueos de privacidad de las apps en modo sandbox.
* **Telemetría Real:** Estadísticas leídas desde la base de datos sin números ficticios.

---

## 🛠️ Estructura del Proyecto

```
mayorclpis/
├── backend/
│   ├── app/                # Servidor FastAPI, SQLite WAL y Jobs en cola (1 worker)
│   ├── clipper/            # Detección de momentos virales y pipeline de recorte
│   ├── higgsfield/         # Conector de cámara cinematográfica y esquema MCP
│   ├── ingest/             # Descarga quirúrgica yt-dlp, heatmap y picos de audio
│   ├── pulpo/              # Router de 7 API Keys Gemini y síntesis de voz neuronal
│   ├── render/             # Motor FFmpeg con aceleración AMF y generador de subtítulos .ass
│   └── skills/             # Skills de Emil Kowalski, Apple Design y HyperFrames
├── frontend/
│   ├── src/
│   │   ├── components/     # Header táctil con glassmorphism
│   │   ├── views/          # Dashboard, Ingesta, Clips, Cámara IA, Publicador, Stats
│   │   └── api.js          # Cliente REST y WebSocket
├── deploy/vps/             # Configuración de Nginx SSL, Systemd daemon y SQL para VPS
├── storage/                # Media, renders y caché local (en .gitignore)
└── INICIAR-MAYORCLIPS.bat  # Iniciador de un solo clic para Windows
```

---

## ⚡ Instalación y Uso Rápido

1. **Requisitos Previos:**
   - Python 3.11+
   - Node.js 18+
   - FFmpeg en el PATH de Windows

2. **Iniciar la aplicación:**
   Haz doble clic sobre:
   ```cmd
   INICIAR-MAYORCLIPS.bat
   ```
   El script arrancará:
   - Backend API: `http://127.0.0.1:8000` (Documentación en `/docs`)
   - Frontend Web: `http://127.0.0.1:5173`

---

## 📄 Licencia

Desarrollado bajo licencia MIT para uso personal y creadores de contenido.
