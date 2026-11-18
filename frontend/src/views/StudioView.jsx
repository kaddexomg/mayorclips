import React, { useState } from "react";
import { Sparkles, CheckCircle2, Loader2, Film, Play, Download } from "lucide-react";
import { api, API_BASE } from "../api";

export default function StudioView() {
  const [topic, setTopic] = useState("");
  const [style, setStyle] = useState("drama");
  const [voice, setVoice] = useState("es-MX-DaliaNeural");
  const [loading, setLoading] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [renderMsg, setRenderMsg] = useState("");
  const [generatedVideo, setGeneratedVideo] = useState(null);

  const handleGenerate = async (e) => {
    e.preventDefault();
    if (!topic.trim()) return;

    setLoading(true);
    try {
      const res = await api.createStudioVideo(topic, style, voice);
      setGeneratedVideo(res);
    } catch (err) {
      alert("Error generando guion: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleRenderMp4 = async () => {
    if (!generatedVideo) return;
    setRendering(true);
    setRenderMsg("Sintetizando voz neuronal y renderizando escenas...");
    try {
      const r = await api.renderStudioVideo(generatedVideo.id);
      const interval = setInterval(async () => {
        try {
          const job = await api.getJobStatus(r.job_id);
          setRenderMsg(`${job.progress || 10}% — ${job.message}`);
          if (job.status === "completed") {
            clearInterval(interval);
            const list = await api.listStudioVideos();
            const updated = list.find((v) => v.id === generatedVideo.id);
            if (updated) setGeneratedVideo(updated);
            setRendering(false);
          } else if (job.status === "failed") {
            clearInterval(interval);
            alert("Error renderizando: " + job.error_message);
            setRendering(false);
          }
        } catch (_) {}
      }, 2000);
    } catch (err) {
      alert(err.message);
      setRendering(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-fadeIn">
      <div className="text-center space-y-2">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-brand/10 border border-brand/20 text-brand text-xs font-mono">
          <Sparkles className="h-3 w-3" /> Estudio Motion Graphics por Código
        </div>
        <h1 className="font-display font-bold text-3xl text-white">
          Escenas Animadas con Personajes y Diálogos IA
        </h1>
        <p className="text-neutral-400 text-sm max-w-xl mx-auto">
          Dramatiza cualquier tema o situación con personajes animados, multitudes, objetos en movimiento, voces distintas para cada actor y subtítulos cinéticos sincronizados.
        </p>
      </div>

      <div className="glass-panel rounded-2xl p-7 space-y-6">
        <form onSubmit={handleGenerate} className="space-y-5">
          <div className="space-y-2">
            <label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">
              Tema o Noticia para el Video
            </label>
            <input
              type="text"
              required
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="Ej: ¿Por qué los aviones nunca vuelan sobre la casa de Messi?"
              className="w-full px-4 py-3 rounded-xl bg-abyss border border-white/10 text-white placeholder-neutral-500 text-sm focus:outline-none focus:border-brand"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">
                Estilo Visual
              </label>
              <select
                value={style}
                onChange={(e) => setStyle(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl bg-abyss border border-white/10 text-white text-xs focus:outline-none focus:border-brand"
              >
                <option value="drama">Dramatización con Personajes y Diálogos</option>
                <option value="history">Historia / Misterio Visual</option>
                <option value="explainer">Explicativo Animado / Código</option>
                <option value="gaming_lore">GTA 6 / Acción & Situaciones Gaming</option>
                <option value="curiosities">Curiosidades Visuales</option>
                <option value="data_charts">Debate con Balanzas & Datos</option>
              </select>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">
                Voz Neuronal (Gratis)
              </label>
              <select
                value={voice}
                onChange={(e) => setVoice(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl bg-abyss border border-white/10 text-white text-xs focus:outline-none focus:border-brand"
              >
                <option value="es-MX-DaliaNeural">Dalia (México — Dinámica)</option>
                <option value="es-MX-JorgeNeural">Jorge (México — Profunda)</option>
                <option value="es-ES-AlvaroNeural">Álvaro (España — Enérgica)</option>
                <option value="es-CO-GonzaloNeural">Gonzalo (Colombia — Neutra)</option>
                <option value="es-AR-TomasNeural">Tomás (Argentina — Moderna)</option>
              </select>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading || !topic.trim()}
            className="btn-tactile w-full py-3.5 rounded-xl bg-brand text-abyss font-display font-bold text-sm hover:brightness-110 disabled:opacity-50 flex items-center justify-center gap-2 shadow-brand-glow"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Escribiendo guion y escenas con Gemini...
              </>
            ) : (
              <>
                <Film className="h-4 w-4 fill-abyss" />
                1. Generar Guion y Escenas
              </>
            )}
          </button>
        </form>

        {generatedVideo && (
          <div className="rounded-xl bg-abyss/80 border border-brand/30 p-5 space-y-4 animate-fadeIn">
            <div className="flex items-center justify-between">
              <h3 className="font-display font-bold text-white text-sm flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-brand" />
                {generatedVideo.title}
              </h3>
              <button
                onClick={handleRenderMp4}
                disabled={rendering}
                className="btn-tactile px-4 py-2 rounded-xl bg-brand text-abyss font-bold text-xs flex items-center gap-1.5 disabled:opacity-50"
              >
                {rendering ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5 fill-abyss" />}
                {rendering ? renderMsg : "2. Renderizar Video MP4"}
              </button>
            </div>

            <div className="p-3.5 rounded-lg bg-ink border border-white/5 text-xs text-neutral-300">
              <span className="text-brand font-bold uppercase font-mono block mb-1">Gancho Inicial:</span>
              "{generatedVideo.script_json?.hook}"
            </div>

            {generatedVideo.video_url && (
              <div className="pt-2 space-y-3">
                <div className="aspect-[9/16] max-w-xs mx-auto rounded-xl overflow-hidden bg-black border border-brand/30">
                  <video src={`${API_BASE}${generatedVideo.video_url}`} controls className="w-full h-full object-contain" />
                </div>
                <div className="text-center space-y-2">
                  <a
                    href={`${API_BASE}${generatedVideo.video_url}`}
                    download={`${generatedVideo.title.slice(0, 30)}.mp4`}
                    className="btn-tactile inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-ink border border-white/10 text-xs text-brand font-mono"
                  >
                    <Download className="h-3.5 w-3.5" /> Descargar MP4
                  </a>
                  {generatedVideo.hf_project_dir && (
                    <div className="text-[11px] font-mono text-neutral-400">
                      Proyecto HyperFrames editable: <span className="text-brand">{generatedVideo.hf_project_dir}</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {generatedVideo.script_json?.characters?.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {generatedVideo.script_json.characters.map((ch) => (
                  <span
                    key={ch.id}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-ink border border-white/10 text-[11px] font-mono text-neutral-200"
                  >
                    <span className="h-2 w-2 rounded-full" style={{ backgroundColor: ch.accent_color || "#2BF0C8" }} />
                    {ch.name} · {ch.archetype}
                  </span>
                ))}
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {generatedVideo.scene_plan_json?.map((sc, i) => {
                const scriptScene = generatedVideo.script_json?.scenes?.[i] || {};
                const dlgs = scriptScene.dialogues || [];
                return (
                  <div key={i} className="p-3.5 rounded-lg bg-ink/70 border border-white/5 space-y-2">
                    <div className="flex items-center justify-between text-[11px] font-mono text-neutral-400">
                      <span>Escena {sc.scene_id || i + 1} · {sc.setting || "plaza"}</span>
                      <span className="text-brand">{sc.crowd_count > 0 ? `👥 ${sc.crowd_count}` : sc.emotion || "drama"}</span>
                    </div>
                    <div className="text-xs text-white font-semibold">{sc.headline || sc.stage_caption}</div>
                    <div className="text-[11px] text-neutral-400">{sc.subtitle || scriptScene.visual_cue}</div>
                    {dlgs.length > 0 && (
                      <div className="space-y-1 pt-1 border-t border-white/5">
                        {dlgs.map((d, di) => (
                          <div key={di} className="text-[11px] text-neutral-300">
                            <span className="text-brand font-mono font-bold">[{d.speaker_id}]:</span> {d.text}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
