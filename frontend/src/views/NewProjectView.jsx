import React, { useState, useRef, useEffect } from "react";
import { Link2, Sparkles, Loader2, AlertCircle, Radio, Upload, FileVideo, Square, PlayCircle } from "lucide-react";
import { api } from "../api";

const JOB_STORAGE_KEY = "mc_active_analyze_job";
const LIVE_STORAGE_KEY = "mc_active_live_proj";

function formatClock(sec) {
  const s = Math.max(0, Math.floor(sec || 0));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${String(m).padStart(2, "0")}:${String(rem).padStart(2, "0")}`;
}

export default function NewProjectView({ setTab, onProjectCreated }) {
  const [mode, setMode] = useState("url"); // "url" | "live" | "file"
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [contextHint, setContextHint] = useState("");
  const [sourceType, setSourceType] = useState("kick");
  const [maxLiveMin, setMaxLiveMin] = useState(5);
  const [localFile, setLocalFile] = useState(null);

  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusMsg, setStatusMsg] = useState("");
  const [error, setError] = useState(null);

  // Live capture state
  const [liveProj, setLiveProj] = useState(null);
  const [liveStatus, setLiveStatus] = useState(null);
  const [stoppingLive, setStoppingLive] = useState(false);

  const pollRef = useRef(null);
  const livePollRef = useRef(null);
  const wsRef = useRef(null);

  const clearTimers = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (livePollRef.current) clearInterval(livePollRef.current);
    if (wsRef.current) wsRef.current.close();
  };

  useEffect(() => {
    // Restore active analyze job or active live capture if user navigated away and came back
    try {
      const savedJob = JSON.parse(sessionStorage.getItem(JOB_STORAGE_KEY) || "null");
      if (savedJob?.jobId && savedJob?.proj) {
        setLoading(true);
        setProgress(savedJob.lastProgress || 15);
        setStatusMsg("Retomando progreso de análisis activo...");
        trackJobProgress(savedJob.jobId, savedJob.proj);
      } else {
        const savedLive = JSON.parse(sessionStorage.getItem(LIVE_STORAGE_KEY) || "null");
        if (savedLive?.id) {
          setMode("live");
          setLiveProj(savedLive);
          startLivePolling(savedLive.id);
        }
      }
    } catch (_) {}

    return clearTimers;
  }, []);

  const handleUrlChange = (e) => {
    const val = e.target.value;
    setUrl(val);
    if (val.includes("twitch.tv")) setSourceType("twitch");
    else if (val.includes("kick.com")) setSourceType("kick");
    else if (val.includes("youtube.com") || val.includes("youtu.be")) setSourceType("youtube");
  };

  const trackJobProgress = (jobId, proj) => {
    let finished = false;
    let pollFailures = 0;
    try {
      sessionStorage.setItem(JOB_STORAGE_KEY, JSON.stringify({ jobId, proj, lastProgress: progress }));
    } catch (_) {}

    const finishSuccess = async () => {
      if (finished) return;
      finished = true;
      sessionStorage.removeItem(JOB_STORAGE_KEY);
      clearTimers();
      const updatedProj = await api.getProject(proj.id).catch(() => proj);
      setLoading(false);
      onProjectCreated(updatedProj);
      setTab("clips");
    };

    const finishError = (errText) => {
      if (finished) return;
      finished = true;
      sessionStorage.removeItem(JOB_STORAGE_KEY);
      clearTimers();
      setLoading(false);
      setError(errText || "Error procesando la transmisión.");
    };

    try {
      const ws = new WebSocket("ws://127.0.0.1:8000/ws/jobs");
      wsRef.current = ws;
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "job_update" && data.job_id === jobId) {
            if (typeof data.progress === "number") setProgress(data.progress);
            if (data.message) setStatusMsg(data.message);
            if (data.status === "completed") finishSuccess();
            else if (data.status === "failed") finishError(data.error || data.message);
          }
        } catch (_) {}
      };
    } catch (_) {}

    pollRef.current = setInterval(async () => {
      try {
        const job = await api.getJobStatus(jobId);
        pollFailures = 0;
        if (typeof job.progress === "number") setProgress(job.progress);
        if (job.message) setStatusMsg(job.message);
        if (job.status === "completed") finishSuccess();
        else if (job.status === "failed") finishError(job.error_message || job.message);
      } catch (e) {
        pollFailures += 1;
        if (pollFailures >= 4) {
          finishError("Se perdió la conexión con el backend durante el análisis. Revisa tus proyectos o vuelve a intentar.");
        }
      }
    }, 2000);
  };

  const startLivePolling = (projectId) => {
    if (livePollRef.current) clearInterval(livePollRef.current);
    livePollRef.current = setInterval(async () => {
      try {
        const st = await api.getLiveStatus(projectId);
        setLiveStatus(st);
        // Auto-stop & analyze when FFmpeg hits max configured duration
        if (st.active && !st.recording && st.elapsed_sec >= 15) {
          clearInterval(livePollRef.current);
          await handleStopLiveAndAnalyze(projectId);
        }
      } catch (_) {}
    }, 2000);
  };

  const handleStopLiveAndAnalyze = async (projIdOverride = null) => {
    const pid = projIdOverride || liveProj?.id;
    if (!pid || stoppingLive) return;
    setStoppingLive(true);
    setError(null);
    if (livePollRef.current) clearInterval(livePollRef.current);
    try {
      const res = await api.stopLiveAndAnalyze(pid);
      sessionStorage.removeItem(LIVE_STORAGE_KEY);
      const savedProj = res.project || liveProj;
      setLiveProj(null);
      setLiveStatus(null);
      setLoading(true);
      setProgress(15);
      setStatusMsg(`Captura en vivo guardada (${Math.round(res.duration_sec || 0)}s). Analizando audio con El Pulpo IA...`);
      trackJobProgress(res.job_id, savedProj);
    } catch (err) {
      setError(err.message);
    } finally {
      setStoppingLive(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if ((mode === "url" || mode === "live") && !url.trim()) return;
    if (mode === "file" && !localFile) return;

    setError(null);

    if (mode === "live") {
      setLoading(true);
      setProgress(8);
      setStatusMsg("Conectando al stream EN VIVO (Twitch / Kick / YouTube)...");
      try {
        const res = await api.startLiveCapture({
          url: url.trim(),
          title: title.trim() || undefined,
          context_hint: contextHint.trim() || undefined,
          max_duration_sec: maxLiveMin * 60,
        });
        setLoading(false);
        setLiveProj(res.project);
        setLiveStatus(res.live);
        sessionStorage.setItem(LIVE_STORAGE_KEY, JSON.stringify(res.project));
        startLivePolling(res.project.id);
      } catch (err) {
        setError(err.message);
        setLoading(false);
      }
      return;
    }

    setLoading(true);
    setProgress(5);
    setStatusMsg(mode === "file" ? "Subiendo archivo de video..." : "Registrando transmisión...");

    try {
      const proj =
        mode === "file"
          ? await api.uploadProjectFile(localFile, title || localFile.name, contextHint.trim())
          : await api.createProject(url.trim(), title.trim() || "Nueva Transmisión", sourceType, contextHint.trim());

      setProgress(12);
      setStatusMsg("Iniciando motor Stream Hunter (0-bloat)...");

      const res = await api.analyzeProject(proj.id);
      trackJobProgress(res.job_id, proj);
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-8 animate-fadeIn">
      <div className="text-center space-y-2">
        <h1 className="font-display font-bold text-3xl text-white">
          Procesar Transmisión, Directo EN VIVO o Video
        </h1>
        <p className="text-neutral-400 text-sm">
          Extrae clips de streams ya terminados (hasta 10h) sin descargar el video entero, o captura fragmentos en tiempo real de directos que están EN VIVO ahora mismo.
        </p>
      </div>

      <div className="glass-panel rounded-2xl p-7 space-y-6">
        {/* Mode Switch: VOD | LIVE | File */}
        <div className="grid grid-cols-3 gap-2 p-1 rounded-xl bg-abyss border border-white/5">
          <button
            type="button"
            disabled={Boolean(liveProj) || loading}
            onClick={() => setMode("url")}
            className={`btn-tactile py-2 rounded-lg text-xs font-medium flex items-center justify-center gap-1.5 ${
              mode === "url" ? "bg-brand text-abyss font-bold" : "text-neutral-400 hover:text-white"
            }`}
          >
            <Link2 className="h-3.5 w-3.5" /> Stream Terminado (VOD)
          </button>
          <button
            type="button"
            disabled={Boolean(liveProj) || loading}
            onClick={() => setMode("live")}
            className={`btn-tactile py-2 rounded-lg text-xs font-medium flex items-center justify-center gap-1.5 ${
              mode === "live" ? "bg-red-500 text-white font-bold" : "text-neutral-400 hover:text-white"
            }`}
          >
            <span className="h-2 w-2 rounded-full bg-current animate-pulse" />
            Directo EN VIVO (Live)
          </button>
          <button
            type="button"
            disabled={Boolean(liveProj) || loading}
            onClick={() => setMode("file")}
            className={`btn-tactile py-2 rounded-lg text-xs font-medium flex items-center justify-center gap-1.5 ${
              mode === "file" ? "bg-brand text-abyss font-bold" : "text-neutral-400 hover:text-white"
            }`}
          >
            <Upload className="h-3.5 w-3.5" /> Archivo Local
          </button>
        </div>

        {/* Active Live Capture Box */}
        {liveProj ? (
          <div className="rounded-xl bg-red-500/10 border border-red-500/40 p-5 space-y-4 animate-fadeIn">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <span className="h-3 w-3 rounded-full bg-red-500 animate-ping" />
                <div>
                  <div className="text-sm font-bold text-white">{liveProj.title}</div>
                  <div className="text-[11px] font-mono text-red-300">
                    CAPTURANDO EN VIVO ({liveStatus?.streamer || "Streamer"})
                  </div>
                </div>
              </div>
              <div className="text-right font-mono">
                <div className="text-sm font-bold text-white">
                  {formatClock(liveStatus?.elapsed_sec)} / {formatClock(maxLiveMin * 60)}
                </div>
                <div className="text-[11px] text-neutral-300">{liveStatus?.file_size_mb || 0} MB grabados</div>
              </div>
            </div>

            <p className="text-xs text-neutral-300 leading-relaxed">
              Cuando termine un momento épico o gracioso en el directo, pulsa el botón de abajo: se detiene la captura y El Pulpo IA analiza inmediatamente todo lo grabado para sacar clips en 9:16 HD.
            </p>

            <button
              type="button"
              disabled={stoppingLive || (liveStatus?.elapsed_sec || 0) < 8}
              onClick={() => handleStopLiveAndAnalyze()}
              className="btn-tactile w-full py-3.5 rounded-xl bg-red-500 hover:bg-red-400 text-white font-display font-bold text-sm disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {stoppingLive ? <Loader2 className="h-4 w-4 animate-spin" /> : <Square className="h-4 w-4 fill-white" />}
              {stoppingLive ? "Cerrando captura y lanzando Pulpo IA..." : "Detener Captura y Extraer Clips Ahora"}
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-5">
            {mode !== "file" ? (
              <>
                {mode === "url" && (
                  <div className="space-y-2">
                    <label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">
                      Plataforma de Origen
                    </label>
                    <div className="grid grid-cols-3 gap-3">
                      {[
                        { id: "kick", label: "Kick VOD / Clip" },
                        { id: "twitch", label: "Twitch VOD / Clip" },
                        { id: "youtube", label: "YouTube Video / Live" },
                      ].map((plat) => (
                        <button
                          type="button"
                          key={plat.id}
                          onClick={() => setSourceType(plat.id)}
                          className={`btn-tactile p-3 rounded-xl border text-xs font-medium text-center flex items-center justify-center gap-2 ${
                            sourceType === plat.id
                              ? "bg-brand/10 border-brand text-brand font-semibold"
                              : "bg-abyss/60 border-white/5 text-neutral-400 hover:border-white/20"
                          }`}
                        >
                          <Radio className={`h-3.5 w-3.5 ${sourceType === plat.id ? "text-brand" : "text-neutral-500"}`} />
                          {plat.label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <div className="space-y-2">
                  <label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">
                    {mode === "live" ? "Enlace del Canal o Directo EN VIVO (Twitch / Kick / YouTube)" : "Enlace del Video o Stream"}
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                      <Link2 className="h-4 w-4 text-neutral-500" />
                    </div>
                    <input
                      type="url"
                      required
                      value={url}
                      onChange={handleUrlChange}
                      placeholder={
                        mode === "live"
                          ? "https://www.twitch.tv/streamer  o  https://kick.com/streamer  o  https://youtube.com/.../live"
                          : "https://www.twitch.tv/videos/...  o  https://kick.com/..."
                      }
                      className="w-full pl-10 pr-4 py-3 rounded-xl bg-abyss border border-white/10 text-white placeholder-neutral-500 text-sm focus:outline-none focus:border-brand font-sans"
                    />
                  </div>
                </div>

                {mode === "live" && (
                  <div className="space-y-2">
                    <label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">
                      Límite Máximo de Captura en Vivo (puedes detenerlo antes cuando quieras)
                    </label>
                    <div className="grid grid-cols-4 gap-2">
                      {[3, 5, 10, 20].map((mins) => (
                        <button
                          type="button"
                          key={mins}
                          onClick={() => setMaxLiveMin(mins)}
                          className={`py-2 rounded-lg border text-xs font-mono ${
                            maxLiveMin === mins
                              ? "bg-red-500/20 border-red-400 text-white font-bold"
                              : "bg-abyss border-white/10 text-neutral-400"
                          }`}
                        >
                          {mins} min
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="space-y-2">
                <label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">
                  Archivo de Video (MP4, MKV, MOV)
                </label>
                <label className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed border-white/15 rounded-xl cursor-pointer bg-abyss/60 hover:border-brand/50 transition">
                  <FileVideo className="h-7 w-7 text-brand mb-2" />
                  <span className="text-xs text-neutral-300 font-medium">
                    {localFile ? `${localFile.name} (${(localFile.size / (1024 * 1024)).toFixed(1)} MB)` : "Haz clic para seleccionar tu video"}
                  </span>
                  <input
                    type="file"
                    accept="video/*"
                    className="hidden"
                    onChange={(e) => setLocalFile(e.target.files?.[0] || null)}
                  />
                </label>
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">
                  Título del Proyecto (Opcional)
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Ej: Atraco GTA V / Charla en Vivo"
                  className="w-full px-4 py-2.5 rounded-xl bg-abyss border border-white/10 text-white placeholder-neutral-500 text-sm focus:outline-none focus:border-brand font-sans"
                />
              </div>

              <div className="space-y-2">
                <label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">
                  Contexto para El Pulpo IA (Opcional)
                </label>
                <input
                  type="text"
                  value={contextHint}
                  onChange={(e) => setContextHint(e.target.value)}
                  placeholder="Ej: Carros, persecuciones GTA, comentarios sobre GTA 6, risas..."
                  className="w-full px-4 py-2.5 rounded-xl bg-abyss border border-white/10 text-white placeholder-neutral-500 text-sm focus:outline-none focus:border-brand font-sans"
                />
                <div className="flex flex-wrap gap-1.5 pt-0.5">
                  {[
                    "Carros, persecuciones y comentarios de GTA 6",
                    "Reacciones sorprendentes y momentos graciosos",
                    "Situaciones inesperadas que den ganas de ver el directo",
                    "Mundo Streamers (RDjavi, Auron, Rubius, IlloJuan)",
                  ].map((preset) => (
                    <button
                      type="button"
                      key={preset}
                      onClick={() => setContextHint(preset)}
                      className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-white/5 hover:bg-brand/15 text-neutral-400 hover:text-brand border border-white/10 transition"
                    >
                      + {preset}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading || (mode === "file" ? !localFile : !url.trim())}
              className={`btn-tactile w-full py-3.5 rounded-xl font-display font-bold text-sm hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 ${
                mode === "live" ? "bg-red-500 text-white" : "bg-brand text-abyss shadow-brand-glow"
              }`}
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Procesando con El Pulpo IA...
                </>
              ) : mode === "live" ? (
                <>
                  <PlayCircle className="h-4 w-4" />
                  Iniciar Captura del Directo EN VIVO
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4 fill-abyss" />
                  Iniciar Análisis Inteligente con El Pulpo
                </>
              )}
            </button>
          </form>
        )}

        {loading && (
          <div className="rounded-xl bg-abyss/80 border border-brand/30 p-4 space-y-3 animate-fadeIn">
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-brand flex items-center gap-2">
                <span className="animate-spin h-3 w-3 border-2 border-brand border-t-transparent rounded-full"></span>
                {statusMsg}
              </span>
              <span className="text-white font-bold">{progress}%</span>
            </div>
            <div className="w-full bg-ink rounded-full h-2 overflow-hidden">
              <div
                className="bg-brand h-full rounded-full transition-all duration-500"
                style={{ width: `${progress}%` }}
              ></div>
            </div>
            <p className="text-[11px] text-neutral-400">
              * Procesamiento concurrente con ventanas de contexto de 120s y respaldo de tiempo de espera por clave.
            </p>
          </div>
        )}

        {error && (
          <div className="rounded-xl bg-red-500/10 border border-red-500/30 p-4 flex items-center gap-3 text-red-400 text-xs font-mono">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}
      </div>
    </div>
  );
}
