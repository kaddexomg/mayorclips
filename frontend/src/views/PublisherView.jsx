import React, { useState, useEffect } from "react";
import { Sparkles, CheckCircle2, Instagram, Facebook, Video, Send, AlertCircle, Loader2, KeyRound } from "lucide-react";
import { api, API_BASE } from "../api";

export default function PublisherView({ selectedClipForPublish, setTab }) {
  const [clips, setClips] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [selectedClipId, setSelectedClipId] = useState(selectedClipForPublish?.id || "");
  const [caption, setCaption] = useState("");
  const [selectedPlatforms, setSelectedPlatforms] = useState(["facebook", "tiktok", "instagram"]);
  const [generatingCopy, setGeneratingCopy] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [publishResults, setPublishResults] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function load() {
      try {
        const [allClips, accs] = await Promise.all([api.listClips(), api.listAccounts()]);
        const readyClips = allClips.filter((c) => c.status === "ready");
        setClips(readyClips);
        setAccounts(accs);
        if (!selectedClipId && readyClips.length > 0) {
          setSelectedClipId(readyClips[0].id);
          setCaption(`${readyClips[0].hook_text || readyClips[0].title}\n\n#viral #clips #streaming`);
        } else if (selectedClipForPublish) {
          const found = readyClips.find((c) => c.id === selectedClipForPublish.id || c.moment_id === selectedClipForPublish.id);
          if (found) {
            setSelectedClipId(found.id);
            setCaption(`${found.hook_text || found.title}\n\n#viral #clips #streaming`);
          }
        }
      } catch (e) {
        console.error(e);
      }
    }
    load();
  }, [selectedClipForPublish]);

  const activeClip = clips.find((c) => c.id === selectedClipId);

  const togglePlatform = (p) => {
    if (selectedPlatforms.includes(p)) {
      setSelectedPlatforms(selectedPlatforms.filter((x) => x !== p));
    } else {
      setSelectedPlatforms([...selectedPlatforms, p]);
    }
  };

  const handleGenerateAiCopy = async () => {
    if (!activeClip) return;
    setGeneratingCopy(true);
    setError(null);
    try {
      const res = await api.writeTitles(activeClip.title, activeClip.hook_text || "");
      setCaption(res.caption_instagram || res.caption_tiktok || res.titles?.[0] || caption);
    } catch (e) {
      setError(e.message);
    } finally {
      setGeneratingCopy(false);
    }
  };

  const handlePublish = async (e) => {
    e.preventDefault();
    if (!selectedClipId) {
      setError("Primero renderiza un clip MP4 en 'Clips Virales' para poder publicarlo.");
      return;
    }
    if (selectedPlatforms.length === 0) {
      setError("Selecciona al menos una red social.");
      return;
    }

    setPublishing(true);
    setError(null);
    setPublishResults(null);
    try {
      const res = await api.createPost({
        media_id: selectedClipId,
        media_type: "clip",
        caption: caption,
        platforms: selectedPlatforms,
      });
      setPublishResults(res.targets || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setPublishing(false);
    }
  };

  const hasAcc = (plat) => accounts.some((a) => a.platform === plat && a.status === "active");

  return (
    <div className="max-w-3xl mx-auto space-y-8 animate-fadeIn">
      <div className="text-center space-y-2">
        <h1 className="font-display font-bold text-3xl text-white">
          Publicador Multi-Red Real
        </h1>
        <p className="text-neutral-400 text-sm">
          Publica tus clips MP4 renderizados simultáneamente en Facebook Reels, TikTok (Inbox 1-Tap Público) e Instagram Reels.
        </p>
      </div>

      <div className="glass-panel rounded-2xl p-7 space-y-6">
        <form onSubmit={handlePublish} className="space-y-6">
          {/* 1. Clip Selector */}
          <div className="space-y-2">
            <label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">
              1. Selecciona el Clip MP4 Renderizado
            </label>
            {clips.length === 0 ? (
              <div className="p-4 rounded-xl bg-abyss border border-dashed border-white/10 text-xs text-neutral-400 flex items-center justify-between">
                <span>No hay clips MP4 renderizados todavía.</span>
                <button
                  type="button"
                  onClick={() => setTab && setTab("clips")}
                  className="text-brand font-mono hover:underline"
                >
                  Ir a Clips →
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-4">
                <select
                  value={selectedClipId}
                  onChange={(e) => setSelectedClipId(e.target.value)}
                  className="flex-1 px-4 py-3 rounded-xl bg-abyss border border-white/10 text-white text-sm focus:outline-none focus:border-brand"
                >
                  {clips.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.title} ({Math.round(c.duration_sec)}s · {c.layout})
                    </option>
                  ))}
                </select>
                {activeClip?.video_url && (
                  <video
                    src={`${API_BASE}${activeClip.video_url}`}
                    className="h-16 w-10 rounded-lg object-cover border border-white/10 bg-black"
                    muted
                  />
                )}
              </div>
            )}
          </div>

          {/* 2. Target Platforms */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">
                2. Redes de Destino
              </label>
              <button
                type="button"
                onClick={() => setTab && setTab("accounts")}
                className="text-xs font-mono text-brand hover:underline flex items-center gap-1"
              >
                <KeyRound className="h-3 w-3" /> Vincular Cuentas
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {[
                { id: "facebook", label: "Facebook Reels", sub: hasAcc("facebook") ? "Conectada" : "Sin vincular", icon: Facebook, color: "text-blue-400" },
                { id: "tiktok", label: "TikTok 1-Tap", sub: hasAcc("tiktok") ? "Conectada" : "Sin vincular", icon: Video, color: "text-brand" },
                { id: "instagram", label: "Instagram Reels", sub: hasAcc("instagram") ? "Conectada" : "Sin vincular", icon: Instagram, color: "text-pink-400" },
              ].map((p) => {
                const Icon = p.icon;
                const active = selectedPlatforms.includes(p.id);
                const linked = hasAcc(p.id);
                return (
                  <div
                    key={p.id}
                    onClick={() => togglePlatform(p.id)}
                    className={`btn-tactile cursor-pointer p-4 rounded-xl border flex items-center justify-between ${
                      active ? "bg-brand/10 border-brand/50 text-white" : "bg-abyss/60 border-white/5 text-neutral-400"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <Icon className={`h-4 w-4 ${p.color}`} />
                      <div>
                        <div className="text-xs font-bold">{p.label}</div>
                        <div className={`text-[10px] font-mono ${linked ? "text-emerald-400" : "text-amber-400"}`}>
                          {p.sub}
                        </div>
                      </div>
                    </div>
                    <input type="checkbox" checked={active} readOnly className="accent-brand" />
                  </div>
                );
              })}
            </div>
          </div>

          {/* 3. Caption */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">
                3. Descripción y Hashtags
              </label>
              <button
                type="button"
                onClick={handleGenerateAiCopy}
                disabled={generatingCopy || !activeClip}
                className="text-xs font-mono text-brand hover:underline flex items-center gap-1 disabled:opacity-50"
              >
                <Sparkles className="h-3 w-3" />
                {generatingCopy ? "Generando con Gemini..." : "Optimizar con El Pulpo IA"}
              </button>
            </div>
            <textarea
              rows={4}
              required
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              className="w-full p-4 rounded-xl bg-abyss border border-white/10 text-white placeholder-neutral-500 text-sm focus:outline-none focus:border-brand"
              placeholder="Descripción y hashtags del clip..."
            />
          </div>

          <button
            type="submit"
            disabled={publishing || !selectedClipId}
            className="btn-tactile w-full py-3.5 rounded-xl bg-brand text-abyss font-display font-bold text-sm hover:brightness-110 disabled:opacity-50 flex items-center justify-center gap-2 shadow-brand-glow"
          >
            {publishing ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Subiendo y publicando...
              </>
            ) : (
              <>
                <Send className="h-4 w-4" />
                Publicar en {selectedPlatforms.length} Redes
              </>
            )}
          </button>
        </form>

        {/* Per-Platform Real API Results */}
        {publishResults && (
          <div className="space-y-2 pt-2 border-t border-white/10 animate-fadeIn">
            <div className="text-xs font-mono text-neutral-400 uppercase">Resultado por Plataforma</div>
            {publishResults.map((r) => (
              <div
                key={r.id}
                className={`p-3 rounded-xl border text-xs font-mono flex items-center justify-between ${
                  r.status === "published" || r.status === "draft_inbox"
                    ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
                    : "bg-red-500/10 border-red-500/30 text-red-300"
                }`}
              >
                <span className="font-bold uppercase">{r.platform}: {r.status}</span>
                <span className="text-[11px] truncate max-w-md">
                  {r.error_message || (r.status === "draft_inbox" ? "Enviado a TikTok Inbox (abre la app para publicar)" : `ID: ${r.remote_post_id}`)}
                </span>
              </div>
            ))}
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
