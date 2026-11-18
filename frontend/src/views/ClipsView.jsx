import React, { useState, useEffect } from "react";
import { Play, Sparkles, Clock, Share2, Video, Sliders, Loader2, Download, Trash2, Plus, CheckCircle2, AlertCircle } from "lucide-react";
import { api, API_BASE } from "../api";

function formatTimecode(sec) {
  const s = Math.max(0, Math.floor(sec || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  return h > 0
    ? `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`
    : `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}

export default function ClipsView({ selectedProject, setTab, onSelectClipForPublish }) {
  const [projects, setProjects] = useState([]);
  const [activeProject, setActiveProject] = useState(selectedProject);
  const [moments, setMoments] = useState([]);
  const [clips, setClips] = useState([]);
  const [loading, setLoading] = useState(true);
  const [renderingId, setRenderingId] = useState(null);
  const [renderProgress, setRenderProgress] = useState({ pct: 0, msg: "" });
  const [error, setError] = useState(null);

  // Editor modal state
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingClip, setEditingClip] = useState(null);
  const [editLayout, setEditLayout] = useState("split_screen");
  const [editSubStyle, setEditSubStyle] = useState("hormozi");
  const [editHook, setEditHook] = useState("");
  const [editEventComment, setEditEventComment] = useState("");
  const [editStart, setEditStart] = useState(0);
  const [editEnd, setEditEnd] = useState(45);

  useEffect(() => {
    setActiveProject(selectedProject);
  }, [selectedProject]);

  const loadData = async () => {
    try {
      setLoading(true);
      const projs = await api.listProjects();
      setProjects(projs);

      const targetProj = activeProject || (projs.length > 0 ? projs[0] : null);
      if (targetProj) {
        const [m, c] = await Promise.all([
          api.getMoments(targetProj.id),
          api.listClips(targetProj.id),
        ]);
        setMoments(m);
        setClips(c);
      } else {
        const c = await api.listClips();
        setMoments([]);
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
  }, [activeProject]);

  // Auto-refresh whenever any clip in list is actively rendering in backend
  useEffect(() => {
    const hasActiveRender = clips.some((c) => c.status === "rendering");
    if (!hasActiveRender) return;
    const t = setInterval(async () => {
      try {
        const pid = activeProject?.id;
        const fresh = await api.listClips(pid || undefined);
        setClips(fresh);
      } catch (_) {}
    }, 2500);
    return () => clearInterval(t);
  }, [clips, activeProject]);

  const trackRenderJob = (jobId, clipId) => {
    const interval = setInterval(async () => {
      try {
        const job = await api.getJobStatus(jobId);
        setRenderProgress({ pct: job.progress || 10, msg: job.message || "Renderizando..." });
        if (job.status === "completed") {
          clearInterval(interval);
          setRenderingId(null);
          await loadData();
        } else if (job.status === "failed") {
          clearInterval(interval);
          setRenderingId(null);
          setError(job.error_message || "Error al renderizar clip");
          await loadData();
        }
      } catch (_) {}
    }, 2000);
  };

  const handleRenderMoment = async (moment, customOverrides = null) => {
    setError(null);
    try {
      setRenderingId(moment.id);
      setRenderProgress({ pct: 5, msg: "Creando clip..." });

      const clip = await api.createClip({
        project_id: moment.project_id,
        moment_id: moment.id,
        title: moment.title,
        hook_text: customOverrides?.hook_text ?? moment.hook,
        event_comment: customOverrides?.event_comment ?? moment.event_comment,
        start_sec: customOverrides?.start_sec ?? moment.start_sec,
        end_sec: customOverrides?.end_sec ?? moment.end_sec,
        layout: customOverrides?.layout ?? "auto",
        subtitle_style: customOverrides?.subtitle_style ?? "hormozi",
      });

      const r = await api.renderClip(clip.id);
      trackRenderJob(r.job_id, clip.id);
    } catch (err) {
      setError(err.message);
      setRenderingId(null);
    }
  };

  const handleReRenderClip = async (clip) => {
    setError(null);
    try {
      setRenderingId(clip.id);
      setRenderProgress({ pct: 5, msg: "Encolando render..." });
      const r = await api.renderClip(clip.id);
      trackRenderJob(r.job_id, clip.id);
    } catch (err) {
      setError(err.message);
      setRenderingId(null);
    }
  };

  const openEditor = (clip) => {
    setEditingClip(clip);
    setEditLayout(clip.layout || "split_screen");
    setEditSubStyle(clip.subtitle_style || "hormozi");
    setEditHook(clip.hook_text || clip.title);
    setEditEventComment(clip.event_comment || "");
    setEditStart(clip.start_sec || 0);
    setEditEnd(clip.end_sec || 45);
    setEditorOpen(true);
  };

  const saveAndRenderEditor = async () => {
    if (!editingClip) return;
    try {
      const updated = await api.updateClip(editingClip.id, {
        layout: editLayout,
        subtitle_style: editSubStyle,
        hook_text: editHook,
        event_comment: editEventComment,
        start_sec: Number(editStart),
        end_sec: Number(editEnd),
      });
      setEditorOpen(false);
      await handleReRenderClip(updated);
    } catch (e) {
      setError(e.message);
    }
  };

  const handleDeleteClip = async (clipId) => {
    try {
      await api.deleteClip(clipId);
      await loadData();
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Header & Project Selector */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="font-display font-bold text-2xl md:text-3xl text-white">
            Clips y Momentos Virales
          </h1>
          <p className="text-neutral-400 text-xs md:text-sm">
            {moments.length} momentos detectados · {clips.filter((c) => c.status === "ready").length} clips MP4 renderizados
          </p>
        </div>

        {projects.length > 0 && (
          <select
            value={activeProject?.id || projects[0]?.id || ""}
            onChange={(e) => {
              const found = projects.find((p) => p.id === e.target.value);
              setActiveProject(found || null);
            }}
            className="px-3.5 py-2 rounded-xl bg-ink border border-white/10 text-xs text-white font-sans focus:outline-none focus:border-brand max-w-xs"
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title} ({p.source_type})
              </option>
            ))}
          </select>
        )}
      </div>

      {error && (
        <div className="rounded-xl bg-red-500/10 border border-red-500/30 p-4 flex items-center gap-3 text-red-400 text-xs font-mono">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {renderingId && (
        <div className="rounded-xl bg-ink/80 border border-brand/40 p-4 space-y-2 animate-fadeIn">
          <div className="flex items-center justify-between text-xs font-mono">
            <span className="text-brand flex items-center gap-2">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {renderProgress.msg}
            </span>
            <span className="text-white font-bold">{renderProgress.pct}%</span>
          </div>
          <div className="w-full bg-abyss rounded-full h-2 overflow-hidden">
            <div className="bg-brand h-full transition-all duration-300" style={{ width: `${renderProgress.pct}%` }}></div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="py-20 text-center space-y-3">
          <Loader2 className="h-8 w-8 text-brand animate-spin mx-auto" />
          <p className="text-xs font-mono text-neutral-400">Cargando clips y momentos...</p>
        </div>
      ) : moments.length === 0 && clips.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-white/10 p-12 text-center space-y-4 bg-ink/20">
          <Video className="h-10 w-10 text-neutral-500 mx-auto" />
          <h3 className="font-display font-semibold text-white">No hay clips generados todavía</h3>
          <p className="text-sm text-neutral-400 max-w-md mx-auto">
            Procesa un enlace de Kick, Twitch o YouTube en la pestaña "Nuevo Stream" para que El Pulpo IA extraiga los momentos virales.
          </p>
          <button
            onClick={() => setTab("new")}
            className="btn-tactile px-5 py-2.5 rounded-xl bg-brand text-abyss font-semibold text-xs shadow-brand-glow"
          >
            Procesar Nuevo Stream
          </button>
        </div>
      ) : (
        <div className="space-y-10">
          {/* SECTION 1: RENDERED MP4 CLIPS READY TO WATCH & PUBLISH */}
          {clips.length > 0 && (
            <div className="space-y-4">
              <h2 className="font-display font-semibold text-lg text-white flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-brand" /> Clips Verticales Renderizados ({clips.length})
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {clips.map((c) => {
                  const isBusy = renderingId === c.id || c.status === "rendering";
                  return (
                    <div key={c.id} className="glass-panel rounded-2xl overflow-hidden flex flex-col justify-between">
                      <div className="relative aspect-[9/16] bg-black flex items-center justify-center border-b border-white/5">
                        {c.status === "ready" && c.video_url ? (
                          <video
                            src={`${API_BASE}${c.video_url}`}
                            poster={c.thumbnail_url ? `${API_BASE}${c.thumbnail_url}` : undefined}
                            controls
                            playsInline
                            className="w-full h-full object-contain bg-black"
                          />
                        ) : (
                          <div className="text-center p-6 space-y-2">
                            {isBusy ? (
                              <Loader2 className="h-8 w-8 text-brand animate-spin mx-auto" />
                            ) : (
                              <Video className="h-8 w-8 text-neutral-500 mx-auto" />
                            )}
                            <p className="text-xs font-mono text-neutral-400">
                              {c.status === "failed" ? `Error: ${c.error_message}` : `Estado: ${c.status}`}
                            </p>
                          </div>
                        )}
                      </div>

                      <div className="p-4 space-y-3">
                        <div>
                          <h3 className="font-display font-semibold text-sm text-white truncate">{c.title}</h3>
                          <div className="text-[11px] font-mono text-neutral-400 flex items-center gap-2 mt-1">
                            <span>{formatTimecode(c.start_sec)} → {formatTimecode(c.end_sec)}</span>
                            <span>·</span>
                            <span className="text-brand">{c.layout}</span>
                            <span>·</span>
                            <span>{c.subtitle_style}</span>
                          </div>
                        </div>

                        <div className="flex items-center gap-2 pt-2 border-t border-white/5">
                          <button
                            onClick={() => openEditor(c)}
                            className="btn-tactile flex-1 py-2 rounded-lg bg-ink border border-white/10 text-xs text-neutral-200 hover:border-brand/40 flex items-center justify-center gap-1.5"
                          >
                            <Sliders className="h-3.5 w-3.5 text-brand" /> Editar
                          </button>

                          {c.video_url && (
                            <a
                              href={`${API_BASE}${c.video_url}`}
                              download={`${c.title.slice(0, 30)}.mp4`}
                              className="btn-tactile p-2 rounded-lg bg-ink border border-white/10 text-neutral-200 hover:text-brand"
                              title="Descargar MP4"
                            >
                              <Download className="h-4 w-4" />
                            </a>
                          )}

                          <button
                            onClick={() => {
                              onSelectClipForPublish(c);
                              setTab("publisher");
                            }}
                            disabled={c.status !== "ready"}
                            className="btn-tactile flex-1 py-2 rounded-lg bg-brand text-abyss font-bold text-xs disabled:opacity-40 flex items-center justify-center gap-1.5"
                          >
                            <Share2 className="h-3.5 w-3.5" /> Publicar
                          </button>

                          <button
                            onClick={() => handleDeleteClip(c.id)}
                            className="btn-tactile p-2 rounded-lg bg-ink border border-white/10 text-neutral-500 hover:text-red-400"
                            title="Eliminar clip"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* SECTION 2: AI DETECTED MOMENTS */}
          {moments.length > 0 && (
            <div className="space-y-4">
              <h2 className="font-display font-semibold text-lg text-white flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-brand" /> Momentos Virales Detectados ({moments.length})
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {moments.map((m) => {
                  const isRendering = renderingId === m.id;
                  return (
                    <div key={m.id} className="glass-panel rounded-2xl overflow-hidden flex flex-col justify-between">
                      <div className="relative p-5 bg-gradient-to-b from-ink/90 to-abyss border-b border-white/5 space-y-3">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-abyss border border-white/10 text-neutral-300 font-mono text-[11px]">
                            <Clock className="h-3 w-3 text-brand" />
                            <span>{formatTimecode(m.start_sec)} – {formatTimecode(m.end_sec)} ({Math.round(m.duration_sec)}s)</span>
                          </div>
                          <div className="flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-brand/10 border border-brand/30 text-brand font-mono text-xs font-bold">
                            <Sparkles className="h-3 w-3" />
                            <span>{m.virality_score}%</span>
                          </div>
                        </div>

                        <div className="pt-2 text-center space-y-2">
                          <div className="inline-block px-3 py-1 rounded-lg bg-brand/15 border border-brand/30 text-brand font-display font-bold text-xs uppercase tracking-wide">
                            "{m.hook}"
                          </div>
                          {m.event_comment && (
                            <div className="text-[11px] font-mono text-amber-300 bg-black/50 px-2.5 py-1 rounded border border-amber-400/20">
                              {m.event_comment}
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="p-5 space-y-4">
                        <div className="space-y-1">
                          <h3 className="font-display font-semibold text-sm text-white line-clamp-1">{m.title}</h3>
                          <p className="text-xs text-neutral-400 line-clamp-3 leading-relaxed">{m.reason}</p>
                        </div>

                        <button
                          disabled={Boolean(renderingId)}
                          onClick={() => handleRenderMoment(m)}
                          className="btn-tactile w-full py-2.5 rounded-xl bg-brand text-abyss font-display font-bold text-xs hover:brightness-110 disabled:opacity-50 flex items-center justify-center gap-1.5 shadow-brand-glow"
                        >
                          {isRendering ? (
                            <>
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              Renderizando 9:16...
                            </>
                          ) : (
                            <>
                              <Play className="h-3.5 w-3.5 fill-abyss" />
                              Crear & Renderizar Clip 9:16
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Editor Modal */}
      {editorOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="max-w-md w-full rounded-2xl bg-ink border border-white/10 p-6 space-y-5 animate-fadeIn">
            <div className="flex items-center justify-between">
              <h3 className="font-display font-bold text-lg text-white flex items-center gap-2">
                <Sliders className="h-4 w-4 text-brand" /> Editar & Re-Renderizar Clip
              </h3>
              <button onClick={() => setEditorOpen(false)} className="text-neutral-400 hover:text-white text-xs font-mono">
                Cerrar ✕
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="font-mono text-neutral-400 uppercase">Inicio (seg)</label>
                  <input
                    type="number"
                    step="1"
                    value={editStart}
                    onChange={(e) => setEditStart(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-abyss border border-white/10 text-white font-mono focus:outline-none focus:border-brand"
                  />
                </div>
                <div className="space-y-1">
                  <label className="font-mono text-neutral-400 uppercase">Fin (seg)</label>
                  <input
                    type="number"
                    step="1"
                    value={editEnd}
                    onChange={(e) => setEditEnd(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-abyss border border-white/10 text-white font-mono focus:outline-none focus:border-brand"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="font-mono text-neutral-400 uppercase">Texto Gancho (Hook)</label>
                <input
                  type="text"
                  value={editHook}
                  onChange={(e) => setEditHook(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-abyss border border-white/10 text-white focus:outline-none focus:border-brand"
                />
              </div>

              <div className="space-y-1">
                <label className="font-mono text-neutral-400 uppercase">Tarjeta de Evento</label>
                <input
                  type="text"
                  value={editEventComment}
                  onChange={(e) => setEditEventComment(e.target.value)}
                  placeholder="Ej: 💀 Momento épico"
                  className="w-full px-3 py-2 rounded-lg bg-abyss border border-white/10 text-white focus:outline-none focus:border-brand"
                />
              </div>

              <div className="space-y-1">
                <label className="font-mono text-neutral-400 uppercase">Layout 9:16</label>
                <select
                  value={editLayout}
                  onChange={(e) => setEditLayout(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-abyss border border-white/10 text-white focus:outline-none focus:border-brand"
                >
                  <option value="auto">Auto Inteligente (Detecta hablantes y pantalla)</option>
                  <option value="duo_split">Dúo Vertical (1 persona arriba / 1 persona abajo)</option>
                  <option value="speaker_focus">Seguimiento al Hablante Activo + Pantalla</option>
                  <option value="split_screen">Webcam Arriba + Juego/Pantalla Abajo</option>
                  <option value="centered_face">Centrado en Hablante (9:16 Full)</option>
                  <option value="blur_bg">Pantalla Completa + Fondo Blur</option>
                </select>
              </div>

              <div className="space-y-1">
                <label className="font-mono text-neutral-400 uppercase">Estilo de Subtítulos</label>
                <select
                  value={editSubStyle}
                  onChange={(e) => setEditSubStyle(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-abyss border border-white/10 text-white focus:outline-none focus:border-brand"
                >
                  <option value="hormozi">Alex Hormozi (Cyan Bold)</option>
                  <option value="neon">Neón Quanty (#2BF0C8)</option>
                  <option value="karaoke">Karaoke Progresivo</option>
                  <option value="mrbeast">MrBeast Pop-Up</option>
                  <option value="minimal">Minimal Blanco</option>
                </select>
              </div>
            </div>

            <button
              onClick={saveAndRenderEditor}
              className="btn-tactile w-full py-2.5 rounded-xl bg-brand text-abyss font-bold text-xs shadow-brand-glow"
            >
              Guardar y Re-Renderizar MP4
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
