import React, { useState, useRef, useEffect } from "react";
import { Link2, Sparkles, Loader2, AlertCircle, Radio, Upload, FileVideo } from "lucide-react";
import { api } from "../api";

export default function NewProjectView({ setTab, onProjectCreated }) {
  const [mode, setMode] = useState("url"); // "url" | "file"
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [sourceType, setSourceType] = useState("kick");
  const [localFile, setLocalFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusMsg, setStatusMsg] = useState("");
  const [error, setError] = useState(null);

  const pollRef = useRef(null);
  const wsRef = useRef(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (wsRef.current) wsRef.current.close();
    };
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

    const finishSuccess = async () => {
      if (finished) return;
      finished = true;
      if (pollRef.current) clearInterval(pollRef.current);
      if (wsRef.current) wsRef.current.close();
      const updatedProj = await api.getProject(proj.id).catch(() => proj);
      setLoading(false);
      onProjectCreated(updatedProj);
      setTab("clips");
    };

    const finishError = (errText) => {
      if (finished) return;
      finished = true;
      if (pollRef.current) clearInterval(pollRef.current);
      if (wsRef.current) wsRef.current.close();
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
            else if (data.status === "failed") finishError(data.error);
          }
        } catch (_) {}
      };
    } catch (_) {}

    // Always keep reliable 2s polling active alongside WebSocket
    pollRef.current = setInterval(async () => {
      try {
        const job = await api.getJobStatus(jobId);
        if (typeof job.progress === "number") setProgress(job.progress);
        if (job.message) setStatusMsg(job.message);
        if (job.status === "completed") finishSuccess();
        else if (job.status === "failed") finishError(job.error_message || job.message);
      } catch (_) {}
    }, 2000);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (mode === "url" && !url.trim()) return;
    if (mode === "file" && !localFile) return;

    setLoading(true);
    setError(null);
    setProgress(5);
    setStatusMsg(mode === "file" ? "Subiendo archivo de video..." : "Registrando transmisión...");

    try {
      const proj =
        mode === "file"
          ? await api.uploadProjectFile(localFile, title || localFile.name)
          : await api.createProject(url.trim(), title.trim() || "Nueva Transmisión", sourceType);

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
          Procesar Transmisión o Video
        </h1>
        <p className="text-neutral-400 text-sm">
          Soporta directos de hasta 10 horas en Kick, Twitch o YouTube sin descargar el video completo. Detecta explosiones del chat y escucha los mejores momentos con El Pulpo IA.
        </p>
      </div>

      <div className="glass-panel rounded-2xl p-7 space-y-6">
        {/* Mode Switch */}
        <div className="grid grid-cols-2 gap-2 p-1 rounded-xl bg-abyss border border-white/5">
          <button
            type="button"
            onClick={() => setMode("url")}
            className={`btn-tactile py-2 rounded-lg text-xs font-medium flex items-center justify-center gap-2 ${
              mode === "url" ? "bg-brand text-abyss font-bold" : "text-neutral-400 hover:text-white"
            }`}
          >
            <Link2 className="h-3.5 w-3.5" /> Enlace (Kick / Twitch / YT)
          </button>
          <button
            type="button"
            onClick={() => setMode("file")}
            className={`btn-tactile py-2 rounded-lg text-xs font-medium flex items-center justify-center gap-2 ${
              mode === "file" ? "bg-brand text-abyss font-bold" : "text-neutral-400 hover:text-white"
            }`}
          >
            <Upload className="h-3.5 w-3.5" /> Subir Archivo Local
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          {mode === "url" ? (
            <>
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

              <div className="space-y-2">
                <label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">
                  Enlace del Video o Directo
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
                    placeholder="https://kick.com/streamer/videos/... o https://youtube.com/watch?v=..."
                    className="w-full pl-10 pr-4 py-3 rounded-xl bg-abyss border border-white/10 text-white placeholder-neutral-500 text-sm focus:outline-none focus:border-brand font-sans"
                  />
                </div>
              </div>
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

          <div className="space-y-2">
            <label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">
              Título del Proyecto (Opcional)
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Ej: Directo Kick Davoo / Torneo Épico"
              className="w-full px-4 py-2.5 rounded-xl bg-abyss border border-white/10 text-white placeholder-neutral-500 text-sm focus:outline-none focus:border-brand font-sans"
            />
          </div>

          <button
            type="submit"
            disabled={loading || (mode === "url" ? !url.trim() : !localFile)}
            className="btn-tactile w-full py-3.5 rounded-xl bg-brand text-abyss font-display font-bold text-sm hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 shadow-brand-glow"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Analizando con El Pulpo IA...
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4 fill-abyss" />
                Iniciar Análisis Inteligente con El Pulpo
              </>
            )}
          </button>
        </form>

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
              * Radar de Chat + Extracción Quirúrgica: analizamos streams largos de hasta 10h escuchando solo los picos clave sin llenar tu disco.
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
