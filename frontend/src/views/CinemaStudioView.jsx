import React, { useState, useEffect } from "react";
import { Clapperboard, Video, MoveRight, MoveLeft, ZoomIn, ZoomOut, RotateCw, Play, Loader2, Sparkles, CheckCircle2 } from "lucide-react";
import { api } from "../api";

export default function CinemaStudioView() {
  const [prompt, setPrompt] = useState("");
  const [motion, setMotion] = useState("zoom_in");
  const [duration, setDuration] = useState(4.0);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [hfStatus, setHfStatus] = useState(null);

  useEffect(() => {
    async function checkStatus() {
      try {
        const s = await api.getHiggsfieldStatus();
        setHfStatus(s);
      } catch (_) {}
    }
    checkStatus();
  }, []);

  const handleGenerate = async (e) => {
    e.preventDefault();
    if (!prompt.trim()) return;

    setLoading(true);
    try {
      const res = await api.generateCinematicBroll(prompt, motion, duration);
      setResult(res);
    } catch (err) {
      console.error(err);
      alert("Error generando B-roll: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  const motions = [
    { id: "zoom_in", label: "Zoom In (Dolly In)", icon: ZoomIn, desc: "Aproximación dramática al centro" },
    { id: "zoom_out", label: "Zoom Out (Reveal)", icon: ZoomOut, desc: "Alejamiento para revelar entorno" },
    { id: "pan_right", label: "Pan Derecha", icon: MoveRight, desc: "Barrido horizontal fluido" },
    { id: "pan_left", label: "Pan Izquierda", icon: MoveLeft, desc: "Barrido hacia la izquierda" },
    { id: "orbit_3d", label: "Órbita 3D Cinematográfica", icon: RotateCw, desc: "Giro orbital tridimensional continuo" },
  ];

  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-fadeIn">
      {/* Hero Header */}
      <div className="text-center space-y-2">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-brand/10 border border-brand/20 text-brand text-xs font-mono">
          <Clapperboard className="h-3.5 w-3.5" />
          <span>Higgsfield Cinematic Studio & Trajectory Controls</span>
        </div>
        <h1 className="font-display font-bold text-3xl text-white">
          B-Roll & Movimientos de Cámara con IA
        </h1>
        <p className="text-neutral-400 text-sm max-w-xl mx-auto">
          Genera transiciones cinematográficas con trayectoria de cámara personalizada (Zoom, Pan, Órbita 3D). Compatible con la API y MCP oficial de Higgsfield.
        </p>
      </div>

      {/* Main Studio Card */}
      <div className="glass-panel rounded-2xl p-7 space-y-6">
        {/* Status pill */}
        <div className="flex items-center justify-between p-3 rounded-xl bg-abyss/80 border border-white/5 text-xs font-mono">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-brand animate-ping"></span>
            <span className="text-neutral-300">
              Modo: <strong className="text-brand">{hfStatus?.mode === "official-mcp" ? "Higgsfield MCP Oficial" : "Open Alternative Cloud + Trajectory"}</strong>
            </span>
          </div>
          <span className="text-[11px] text-neutral-500">Zero-VRAM en Ryzen 5</span>
        </div>

        <form onSubmit={handleGenerate} className="space-y-6">
          {/* Prompt */}
          <div className="space-y-2">
            <label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">
              1. Descripción de la Escena Cinematográfica
            </label>
            <input
              type="text"
              required
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Ej: Neon cyberpunk street at night with dramatic rain reflections and reflections in vertical 9:16"
              className="w-full px-4 py-3 rounded-xl bg-abyss border border-white/10 text-white placeholder-neutral-500 text-sm focus:outline-none focus:border-brand font-sans transition"
            />
          </div>

          {/* Camera Motion Selection */}
          <div className="space-y-3">
            <label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">
              2. Trayectoria y Control de Cámara
            </label>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {motions.map((m) => {
                const Icon = m.icon;
                const active = motion === m.id;
                return (
                  <button
                    type="button"
                    key={m.id}
                    onClick={() => setMotion(m.id)}
                    className={`btn-tactile p-3.5 rounded-xl border text-left flex flex-col justify-between space-y-2 ${
                      active
                        ? "bg-brand/10 border-brand text-white shadow-brand-glow"
                        : "bg-abyss/50 border-white/5 text-neutral-400 hover:border-white/20"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className={`text-xs font-bold font-sans ${active ? "text-brand" : "text-neutral-200"}`}>
                        {m.label}
                      </span>
                      <Icon className={`h-4 w-4 ${active ? "text-brand" : "text-neutral-500"}`} />
                    </div>
                    <p className="text-[11px] text-neutral-400 leading-tight">
                      {m.desc}
                    </p>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Generate Button */}
          <button
            type="submit"
            disabled={loading || !prompt.trim()}
            className="btn-tactile w-full py-3.5 rounded-xl bg-brand text-abyss font-display font-bold text-sm hover:brightness-110 disabled:opacity-50 transition flex items-center justify-center gap-2 shadow-brand-glow"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Renderizando toma cinematográfica con control de cámara...
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4 fill-abyss" />
                Generar B-Roll Cinematográfico (9:16)
              </>
            )}
          </button>
        </form>

        {/* Video Player Preview */}
        {result && (
          <div className="rounded-xl bg-abyss p-5 border border-brand/30 space-y-4 animate-fadeIn">
            <div className="flex items-center justify-between">
              <h3 className="font-display font-semibold text-white text-sm flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-brand" /> Toma Generada con Éxito
              </h3>
              <span className="text-xs font-mono text-brand uppercase">
                {result.motion_applied}
              </span>
            </div>

            <div className="relative aspect-[9/16] max-w-xs mx-auto rounded-xl overflow-hidden bg-black border border-white/10 shadow-2xl">
              <video
                src={`http://127.0.0.1:8000${result.video_url}`}
                controls
                autoPlay
                loop
                muted
                className="w-full h-full object-cover"
              />
            </div>

            <p className="text-center text-xs text-neutral-400 font-mono">
              * Archivo guardado listo para insertarse en tus clips verticales de MayorClips.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
