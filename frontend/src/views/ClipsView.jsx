import React, { useState, useEffect } from "react";
import { Play, Sparkles, CheckCircle2, Clock, Share2, Video, Sliders, Loader2, AlertCircle } from "lucide-react";
import { api } from "../api";

export default function ClipsView({ selectedProject, setTab, onSelectClipForPublish }) {
  const [moments, setMoments] = useState([]);
  const [clips, setClips] = useState([]);
  const [loading, setLoading] = useState(true);
  const [renderingClipId, setRenderingClipId] = useState(null);
  const [selectedClip, setSelectedClip] = useState(null);
  const [editorOpen, setEditorOpen] = useState(false);

  // Edit fields
  const [editLayout, setEditLayout] = useState("split_screen");
  const [editSubStyle, setEditSubStyle] = useState("hormozi");
  const [editHook, setEditHook] = useState("");
  const [editEventComment, setEditEventComment] = useState("");

  const loadData = async () => {
    try {
      setLoading(true);
      if (selectedProject) {
        const m = await api.getMoments(selectedProject.id);
        const c = await api.listClips(selectedProject.id);
        setMoments(m);
        setClips(c);
      } else {
        const c = await api.listClips();
        setClips(c);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [selectedProject]);

  const handleCreateAndRender = async (moment) => {
    try {
      setRenderingClipId(moment.id);
      // 1. Create clip record
      const clip = await api.createClip({
        project_id: moment.project_id,
        moment_id: moment.id,
        title: moment.title,
        hook_text: moment.hook,
        event_comment: moment.event_comment,
        start_sec: moment.start_sec,
        end_sec: moment.end_sec,
        layout: "split_screen",
        subtitle_style: "hormozi",
      });

      // 2. Trigger render
      await api.renderClip(clip.id);

      // 3. Poll until ready
      const checkInterval = setInterval(async () => {
        const updated = await api.getClip(clip.id);
        if (updated.status === "ready") {
          clearInterval(checkInterval);
          setRenderingClipId(null);
          loadData();
        }
      }, 2500);

    } catch (err) {
      console.error(err);
      setRenderingClipId(null);
    }
  };

  const openEditor = (clip) => {
    setSelectedClip(clip);
    setEditLayout(clip.layout || "split_screen");
    setEditSubStyle(clip.subtitle_style || "hormozi");
    setEditHook(clip.hook_text || clip.title);
    setEditEventComment(clip.event_comment || "");
    setEditorOpen(true);
  };

  const saveEditor = async () => {
    if (!selectedClip) return;
    try {
      await api.updateClip(selectedClip.id, {
        layout: editLayout,
        subtitle_style: editSubStyle,
        hook_text: editHook,
        event_comment: editEventComment,
      });
      setEditorOpen(false);
      loadData();
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="font-display font-bold text-2xl md:text-3xl text-white">
            Clips y Momentos Virales
          </h1>
          <p className="text-neutral-400 text-xs md:text-sm">
            {selectedProject
              ? `Resultados para: ${selectedProject.title}`
              : "Todos los clips listos para previsualizar y publicar"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-neutral-400">
            {moments.length} Momentos encontrados · {clips.length} Clips renderizados
          </span>
        </div>
      </div>

      {loading ? (
        <div className="py-20 text-center space-y-3">
          <Loader2 className="h-8 w-8 text-brand animate-spin mx-auto" />
          <p className="text-xs font-mono text-neutral-400">Cargando biblioteca de clips...</p>
        </div>
      ) : moments.length === 0 && clips.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-white/10 p-12 text-center space-y-4 bg-ink/20">
          <Video className="h-10 w-10 text-neutral-500 mx-auto" />
          <h3 className="font-display font-semibold text-white">No hay clips generados todavía</h3>
          <p className="text-sm text-neutral-400 max-w-md mx-auto">
            Selecciona una transmisión existente desde el Dashboard o añade un nuevo stream para que el Pulpo IA detecte los momentos virales.
          </p>
          <button
            onClick={() => setTab("new")}
            className="px-5 py-2.5 rounded-xl bg-brand text-abyss font-semibold text-xs shadow-brand-glow"
          >
            Añadir Transmisión
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {/* Moments Cards */}
          {moments.map((m) => {
            const isRendering = renderingClipId === m.id;
            return (
              <div
                key={m.id}
                className="rounded-2xl bg-ink/50 border border-white/10 overflow-hidden hover:border-brand/40 transition-all duration-300 flex flex-col justify-between group shadow-card-glow"
              >
                {/* 9:16 Thumbnail Container Preview */}
                <div className="relative aspect-[9/14] bg-abyss flex items-center justify-center overflow-hidden border-b border-white/5">
                  <div className="absolute inset-0 bg-gradient-to-t from-abyss via-transparent to-black/60 z-10"></div>
                  
                  {/* Virality Badge Top Right */}
                  <div className="absolute top-3 right-3 z-20 flex items-center gap-1 px-2.5 py-1 rounded-full bg-abyss/80 border border-brand/40 text-brand font-mono text-xs font-bold shadow-brand-glow">
                    <Sparkles className="h-3 w-3" />
                    <span>{m.virality_score}% Viral</span>
                  </div>

                  {/* Duration Top Left */}
                  <div className="absolute top-3 left-3 z-20 flex items-center gap-1 px-2 py-0.5 rounded-md bg-abyss/70 border border-white/10 text-neutral-300 font-mono text-[11px]">
                    <Clock className="h-3 w-3 text-neutral-400" />
                    <span>{Math.round(m.duration_sec)}s</span>
                  </div>

                  {/* Center Hook Text Preview */}
                  <div className="relative z-20 text-center px-4 space-y-2">
                    <div className="inline-block px-3 py-1 rounded-lg bg-brand/20 border border-brand/30 text-brand font-display font-extrabold text-sm uppercase tracking-wide drop-shadow">
                      "{m.hook}"
                    </div>
                    {m.event_comment && (
                      <div className="text-[11px] font-mono text-amber-300 bg-black/60 px-2 py-0.5 rounded border border-amber-400/20">
                        {m.event_comment}
                      </div>
                    )}
                  </div>
                </div>

                {/* Card Info & Actions */}
                <div className="p-5 space-y-4">
                  <div className="space-y-1">
                    <h3 className="font-display font-semibold text-sm text-white group-hover:text-brand transition line-clamp-1">
                      {m.title}
                    </h3>
                    <p className="text-xs text-neutral-400 line-clamp-2 leading-relaxed">
                      {m.reason}
                    </p>
                  </div>

                  <div className="flex items-center gap-2 pt-2 border-t border-white/5">
                    <button
                      disabled={isRendering}
                      onClick={() => handleCreateAndRender(m)}
                      className="flex-1 py-2.5 rounded-xl bg-brand text-abyss font-display font-bold text-xs hover:brightness-110 disabled:opacity-50 transition flex items-center justify-center gap-1.5 shadow-brand-glow"
                    >
                      {isRendering ? (
                        <>
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          Renderizando...
                        </>
                      ) : (
                        <>
                          <Play className="h-3.5 w-3.5 fill-abyss" />
                          Renderizar 9:16
                        </>
                      )}
                    </button>
                    <button
                      onClick={() => {
                        onSelectClipForPublish(m);
                        setTab("publisher");
                      }}
                      className="p-2.5 rounded-xl bg-ink border border-white/10 text-neutral-300 hover:text-brand hover:border-brand/40 transition"
                      title="Publicar en Redes"
                    >
                      <Share2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Editor Modal */}
      {editorOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="max-w-md w-full rounded-2xl bg-ink border border-white/10 p-6 space-y-5 animate-fadeIn">
            <div className="flex items-center justify-between">
              <h3 className="font-display font-bold text-lg text-white flex items-center gap-2">
                <Sliders className="h-4 w-4 text-brand" /> Personalizar Clip
              </h3>
              <button
                onClick={() => setEditorOpen(false)}
                className="text-neutral-400 hover:text-white text-xs font-mono"
              >
                Cerrar ✕
              </button>
            </div>

            <div className="space-y-4 text-xs">
              <div className="space-y-1.5">
                <label className="font-mono text-neutral-400 uppercase">Texto Gancho (Hook)</label>
                <input
                  type="text"
                  value={editHook}
                  onChange={(e) => setEditHook(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-abyss border border-white/10 text-white font-sans focus:outline-none focus:border-brand"
                />
              </div>

              <div className="space-y-1.5">
                <label className="font-mono text-neutral-400 uppercase">Comentario de Evento</label>
                <input
                  type="text"
                  value={editEventComment}
                  onChange={(e) => setEditEventComment(e.target.value)}
                  placeholder="Ej: 💀 Momento de máxima tensión"
                  className="w-full px-3 py-2 rounded-lg bg-abyss border border-white/10 text-white font-sans focus:outline-none focus:border-brand"
                />
              </div>

              <div className="space-y-1.5">
                <label className="font-mono text-neutral-400 uppercase">Layout 9:16</label>
                <select
                  value={editLayout}
                  onChange={(e) => setEditLayout(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-abyss border border-white/10 text-white font-sans focus:outline-none focus:border-brand"
                >
                  <option value="split_screen">Split Screen (Cam arriba + Juego abajo)</option>
                  <option value="centered_face">Centrado en Hablante</option>
                  <option value="blur_bg">Fondo Desenfoque Viral</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="font-mono text-neutral-400 uppercase">Estilo de Subtítulos</label>
                <select
                  value={editSubStyle}
                  onChange={(e) => setEditSubStyle(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-abyss border border-white/10 text-white font-sans focus:outline-none focus:border-brand"
                >
                  <option value="hormozi">Alex Hormozi (Cyan Bold)</option>
                  <option value="neon">Neón Quanty (#2BF0C8)</option>
                  <option value="karaoke">Karaoke Progresivo</option>
                  <option value="mrbeast">MrBeast Pop-Up</option>
                  <option value="minimal">Minimal Blanco</option>
                </select>
              </div>
            </div>

            <div className="flex items-center gap-2 pt-2">
              <button
                onClick={saveEditor}
                className="w-full py-2.5 rounded-xl bg-brand text-abyss font-semibold text-xs shadow-brand-glow"
              >
                Guardar Ajustes
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
