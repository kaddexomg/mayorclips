import React, { useState } from "react";
import { Link2, Sparkles, Loader2, CheckCircle2, AlertCircle, Radio, Play } from "lucide-react";
import { api } from "../api";

export default function NewProjectView({ setTab, onProjectCreated }) {
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [sourceType, setSourceType] = useState("youtube");
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusMsg, setStatusMsg] = useState("");
  const [error, setError] = useState(null);

  // Auto-detect source platform from URL
  const handleUrlChange = (e) => {
    const val = e.target.value;
    setUrl(val);
    if (val.includes("twitch.tv")) setSourceType("twitch");
    else if (val.includes("kick.com")) setSourceType("kick");
    else if (val.includes("youtube.com") || val.includes("youtu.be")) setSourceType("youtube");
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!url.trim()) return;

    setLoading(true);
    setError(null);
    setProgress(5);
    setStatusMsg("Registrando proyecto...");

    try {
      // 1. Create project
      const proj = await api.createProject(url, title || "Nueva Transmisión", sourceType);
      setProgress(15);
      setStatusMsg("Conectando con el stream e iniciando pipeline de IA...");

      // 2. Trigger analysis
      const res = await api.analyzeProject(proj.id);
      
      // 3. Connect to WebSocket for live job progress
      const ws = new WebSocket("ws://127.0.0.1:8000/ws/jobs");
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "job_update" && data.job_id === res.job_id) {
            setProgress(data.progress || 20);
            setStatusMsg(data.message || "Procesando...");
            if (data.status === "completed") {
              ws.close();
              setLoading(false);
              onProjectCreated(proj);
              setTab("clips");
            } else if (data.status === "failed") {
              ws.close();
              setLoading(false);
              setError(data.error || "Ocurrió un error en el pipeline");
            }
          }
        } catch (_) {}
      };

      ws.onerror = () => {
        // Fallback polling if ws fails
        const interval = setInterval(async () => {
          try {
            const updated = await api.getProject(proj.id);
            if (updated.status === "ready") {
              clearInterval(interval);
              setLoading(false);
              onProjectCreated(updated);
              setTab("clips");
            }
          } catch (_) {}
        }, 3000);
      };

    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-8 animate-fadeIn">
      <div className="text-center space-y-2">
        <h1 className="font-display font-bold text-3xl text-white">
          Procesar Transmisión o VOD
        </h1>
        <p className="text-neutral-400 text-sm">
          Pega el enlace de un directo de Twitch, Kick o un video de YouTube. El pipeline audio-first descargará únicamente los datos necesarios y el Pulpo IA encontrará los momentos más virales.
        </p>
      </div>

      <div className="rounded-2xl bg-ink/70 border border-white/10 p-7 shadow-card-glow space-y-6">
        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Platform Selector Buttons */}
          <div className="space-y-2">
            <label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">
              Plataforma de Origen
            </label>
            <div className="grid grid-cols-3 gap-3">
              {[
                { id: "twitch", label: "Twitch VOD / Clip", color: "border-purple-500/40 text-purple-300" },
                { id: "kick", label: "Kick Stream", color: "border-emerald-500/40 text-emerald-300" },
                { id: "youtube", label: "YouTube Video / Live", color: "border-red-500/40 text-red-300" },
              ].map((plat) => (
                <button
                  type="button"
                  key={plat.id}
                  onClick={() => setSourceType(plat.id)}
                  className={`p-3 rounded-xl border text-xs font-medium transition text-center flex items-center justify-center gap-2 ${
                    sourceType === plat.id
                      ? "bg-brand/10 border-brand text-brand font-semibold shadow-sm"
                      : "bg-abyss/60 border-white/5 text-neutral-400 hover:border-white/20"
                  }`}
                >
                  <Radio className={`h-3.5 w-3.5 ${sourceType === plat.id ? "text-brand" : "text-neutral-500"}`} />
                  {plat.label}
                </button>
              ))}
            </div>
          </div>

          {/* URL Input */}
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
                placeholder="https://www.twitch.tv/videos/... o https://youtube.com/watch?v=..."
                className="w-full pl-10 pr-4 py-3 rounded-xl bg-abyss border border-white/10 text-white placeholder-neutral-500 text-sm focus:outline-none focus:border-brand focus:ring-1 focus:ring-brand font-sans transition"
              />
            </div>
          </div>

          {/* Optional Title */}
          <div className="space-y-2">
            <label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">
              Título del Proyecto (Opcional)
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Ej: Torneo de Minecraft / Directo Épico con Reacciones"
              className="w-full px-4 py-2.5 rounded-xl bg-abyss border border-white/10 text-white placeholder-neutral-500 text-sm focus:outline-none focus:border-brand font-sans transition"
            />
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={loading || !url.trim()}
            className="w-full py-3.5 rounded-xl bg-brand text-abyss font-display font-bold text-sm hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed transition flex items-center justify-center gap-2 shadow-brand-glow"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Procesando transmisión con IA...
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4 fill-abyss" />
                Iniciar Análisis Inteligente con El Pulpo
              </>
            )}
          </button>
        </form>

        {/* Live Progress Bar */}
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
              * Pipeline Audio-First: descargando únicamente el audio y picos de volumen para ahorrar recursos de tu procesador Ryzen 5.
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
