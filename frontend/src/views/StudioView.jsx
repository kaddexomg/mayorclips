import React, { useState } from "react";
import { Sparkles, Layers, Play, CheckCircle2, Loader2, Code, Film } from "lucide-react";
import { api } from "../api";

export default function StudioView() {
  const [topic, setTopic] = useState("");
  const [style, setStyle] = useState("curiosities");
  const [loading, setLoading] = useState(false);
  const [generatedVideo, setGeneratedVideo] = useState(null);

  const handleGenerate = async (e) => {
    e.preventDefault();
    if (!topic.trim()) return;

    setLoading(true);
    try {
      const res = await api.createStudioVideo(topic, style);
      setGeneratedVideo(res);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-fadeIn">
      <div className="text-center space-y-2">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-brand/10 border border-brand/20 text-brand text-xs font-mono">
          <Sparkles className="h-3 w-3" /> Estudio Motion Graphics por Código
        </div>
        <h1 className="font-display font-bold text-3xl text-white">
          Videos Virales con IA y HyperFrames
        </h1>
        <p className="text-neutral-400 text-sm max-w-xl mx-auto">
          Crea videos faceless de alto impacto a partir de un tema o guion. La IA compone escenas HTML/CSS/GSAP mediante plantillas cinéticas y voz neuronal.
        </p>
      </div>

      {/* Creation Form */}
      <div className="rounded-2xl bg-ink/70 border border-white/10 p-7 shadow-card-glow space-y-6">
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
              className="w-full px-4 py-3 rounded-xl bg-abyss border border-white/10 text-white placeholder-neutral-500 text-sm focus:outline-none focus:border-brand font-sans transition"
            />
          </div>

          <div className="space-y-2">
            <label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">
              Estilo Visual & Formato
            </label>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { id: "curiosities", label: "Curiosidades" },
                { id: "top5", label: "Top 5 Virales" },
                { id: "history", label: "Historia / Misterio" },
                { id: "data_charts", label: "Gráficas & Datos" },
              ].map((st) => (
                <button
                  type="button"
                  key={st.id}
                  onClick={() => setStyle(st.id)}
                  className={`p-3 rounded-xl border text-xs font-medium transition text-center ${
                    style === st.id
                      ? "bg-brand/10 border-brand text-brand font-semibold shadow-sm"
                      : "bg-abyss/60 border-white/5 text-neutral-400 hover:border-white/20"
                  }`}
                >
                  {st.label}
                </button>
              ))}
            </div>
          </div>

          <button
            type="submit"
            disabled={loading || !topic.trim()}
            className="w-full py-3.5 rounded-xl bg-brand text-abyss font-display font-bold text-sm hover:brightness-110 disabled:opacity-50 transition flex items-center justify-center gap-2 shadow-brand-glow"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Diseñando guion y escenas en HyperFrames con IA...
              </>
            ) : (
              <>
                <Film className="h-4 w-4 fill-abyss" />
                Generar Video Motion Graphics
              </>
            )}
          </button>
        </form>

        {/* Scene Plan Preview */}
        {generatedVideo && (
          <div className="rounded-xl bg-abyss/80 border border-brand/30 p-5 space-y-4 animate-fadeIn">
            <div className="flex items-center justify-between">
              <h3 className="font-display font-bold text-white text-sm flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-brand" />
                {generatedVideo.title}
              </h3>
              <span className="text-xs font-mono text-brand px-2 py-0.5 rounded bg-brand/10 border border-brand/20">
                Guion y Escenas Listas
              </span>
            </div>

            {/* Hook text */}
            <div className="p-3.5 rounded-lg bg-ink border border-white/5 text-xs text-neutral-300">
              <span className="text-brand font-bold uppercase font-mono block mb-1">Gancho Inicial:</span>
              "{generatedVideo.script_json?.hook}"
            </div>

            {/* Scenes List */}
            <div className="space-y-2">
              <div className="text-xs font-mono text-neutral-400 uppercase">
                Escenas Compuestas ({generatedVideo.scene_plan_json?.length || 0})
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                {generatedVideo.scene_plan_json?.map((sc, i) => (
                  <div key={i} className="p-3 rounded-lg bg-ink/60 border border-white/5 space-y-1">
                    <div className="flex items-center justify-between text-[11px] font-mono text-neutral-400">
                      <span>Escena {sc.scene_id || i + 1}</span>
                      <span className="text-brand">{sc.template || "kinetic_text"}</span>
                    </div>
                    <div className="text-xs text-white font-medium">{sc.headline || sc.spoken_text}</div>
                    <div className="text-[11px] text-neutral-400 line-clamp-1">{sc.subtitle || sc.visual_cue}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
