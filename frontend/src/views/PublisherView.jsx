import React, { useState } from "react";
import { Share2, Sparkles, CheckCircle2, Instagram, Facebook, Video, Send, Clock, AlertCircle, Loader2 } from "lucide-react";
import { api } from "../api";

export default function PublisherView({ selectedClipForPublish }) {
  const [caption, setCaption] = useState(
    selectedClipForPublish?.hook
      ? `${selectedClipForPublish.hook.toUpperCase()} 😱 No te pierdas este momento viral.\n\n#viral #streamer #clips #humor #gaming`
      : "¡Mira este momento épico! 💥\n\n#clips #streamer #viral"
  );
  const [selectedPlatforms, setSelectedPlatforms] = useState(["instagram", "facebook", "tiktok"]);
  const [generatingCopy, setGeneratingCopy] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState(null);

  const togglePlatform = (p) => {
    if (selectedPlatforms.includes(p)) {
      setSelectedPlatforms(selectedPlatforms.filter((x) => x !== p));
    } else {
      setSelectedPlatforms([...selectedPlatforms, p]);
    }
  };

  const handleGenerateAiCopy = async () => {
    setGeneratingCopy(true);
    setError(null);
    try {
      // In a real call this reaches Pulpo write_titles
      setCaption(
        `POV: Cuando crees que tienes la jugada perfecta y pasa esto 💀\n\n¿A ti también te ha pasado? Déjamelo en los comentarios 👇\n\n#streamer #gamingfails #viralclips #fyp #gaming`
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setGeneratingCopy(false);
    }
  };

  const handlePublish = async (e) => {
    e.preventDefault();
    if (selectedPlatforms.length === 0) {
      setError("Selecciona al menos una red social para publicar.");
      return;
    }

    setPublishing(true);
    setError(null);
    try {
      await api.createPost({
        media_id: selectedClipForPublish?.id || "sample-clip-id",
        media_type: "clip",
        caption: caption,
        platforms: selectedPlatforms,
      });
      setSuccess(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setPublishing(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-8 animate-fadeIn">
      <div className="text-center space-y-2">
        <h1 className="font-display font-bold text-3xl text-white">
          Publicador Multi-Red Soberano
        </h1>
        <p className="text-neutral-400 text-sm">
          Un solo clic para distribuir tu clip simultáneamente en Instagram, Facebook y TikTok con las mejores prácticas de cada algoritmo.
        </p>
      </div>

      <div className="rounded-2xl bg-ink/70 border border-white/10 p-7 shadow-card-glow space-y-6">
        <form onSubmit={handlePublish} className="space-y-6">
          {/* Target Platforms Checkboxes */}
          <div className="space-y-3">
            <label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">
              1. Selecciona las redes de destino
            </label>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {/* Instagram */}
              <div
                onClick={() => togglePlatform("instagram")}
                className={`cursor-pointer p-4 rounded-xl border transition flex items-center justify-between ${
                  selectedPlatforms.includes("instagram")
                    ? "bg-gradient-to-br from-pink-500/10 to-purple-500/10 border-pink-500/50 text-white"
                    : "bg-abyss/60 border-white/5 text-neutral-400 hover:border-white/20"
                }`}
              >
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-pink-500/20 text-pink-400">
                    <Instagram className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="text-xs font-bold font-sans">Instagram Reels</div>
                    <div className="text-[10px] text-emerald-400 font-mono">Público Directo</div>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={selectedPlatforms.includes("instagram")}
                  readOnly
                  className="rounded text-brand focus:ring-brand accent-brand"
                />
              </div>

              {/* Facebook */}
              <div
                onClick={() => togglePlatform("facebook")}
                className={`cursor-pointer p-4 rounded-xl border transition flex items-center justify-between ${
                  selectedPlatforms.includes("facebook")
                    ? "bg-blue-500/10 border-blue-500/50 text-white"
                    : "bg-abyss/60 border-white/5 text-neutral-400 hover:border-white/20"
                }`}
              >
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-blue-500/20 text-blue-400">
                    <Facebook className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="text-xs font-bold font-sans">Facebook Reels</div>
                    <div className="text-[10px] text-emerald-400 font-mono">Página Oficial</div>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={selectedPlatforms.includes("facebook")}
                  readOnly
                  className="rounded text-brand focus:ring-brand accent-brand"
                />
              </div>

              {/* TikTok */}
              <div
                onClick={() => togglePlatform("tiktok")}
                className={`cursor-pointer p-4 rounded-xl border transition flex items-center justify-between ${
                  selectedPlatforms.includes("tiktok")
                    ? "bg-brand/10 border-brand/50 text-white"
                    : "bg-abyss/60 border-white/5 text-neutral-400 hover:border-white/20"
                }`}
              >
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-brand/20 text-brand">
                    <Video className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="text-xs font-bold font-sans">TikTok Inbox</div>
                    <div className="text-[10px] text-brand font-mono">1-Tap Público</div>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={selectedPlatforms.includes("tiktok")}
                  readOnly
                  className="rounded text-brand focus:ring-brand accent-brand"
                />
              </div>
            </div>
          </div>

          {/* TikTok Notice Banner */}
          {selectedPlatforms.includes("tiktok") && (
            <div className="rounded-xl bg-brand/5 border border-brand/20 p-3.5 flex items-start gap-3 text-xs text-neutral-300">
              <span className="text-brand text-base leading-none">💡</span>
              <p className="leading-relaxed">
                <strong className="text-brand">Modo TikTok 1-Tap Público Activo:</strong> El video se carga directamente en la bandeja de creador de tu aplicación TikTok. Al abrir la notificación sólo tocas "Publicar" y sale <strong className="text-white">100% público</strong> de forma inmediata, sin bloqueos de privacidad.
              </p>
            </div>
          )}

          {/* Caption & Copywriting Area */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-mono text-neutral-400 uppercase tracking-wider">
                2. Descripción y Hashtags
              </label>
              <button
                type="button"
                onClick={handleGenerateAiCopy}
                disabled={generatingCopy}
                className="text-xs font-mono text-brand hover:underline flex items-center gap-1 disabled:opacity-50"
              >
                <Sparkles className="h-3 w-3" />
                {generatingCopy ? "Generando con IA..." : "Optimizar con El Pulpo IA"}
              </button>
            </div>
            <textarea
              rows={5}
              required
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              className="w-full p-4 rounded-xl bg-abyss border border-white/10 text-white placeholder-neutral-500 text-sm focus:outline-none focus:border-brand font-sans leading-relaxed"
              placeholder="Escribe la descripción de tu publicación..."
            />
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={publishing}
            className="w-full py-3.5 rounded-xl bg-brand text-abyss font-display font-bold text-sm hover:brightness-110 disabled:opacity-50 transition flex items-center justify-center gap-2 shadow-brand-glow"
          >
            {publishing ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Publicando en las redes seleccionadas...
              </>
            ) : (
              <>
                <Send className="h-4 w-4" />
                Publicar Ahora en {selectedPlatforms.length} Redes
              </>
            )}
          </button>
        </form>

        {success && (
          <div className="rounded-xl bg-emerald-500/10 border border-emerald-500/30 p-4 flex items-center gap-3 text-emerald-400 text-xs font-mono animate-fadeIn">
            <CheckCircle2 className="h-5 w-5 shrink-0" />
            <div>
              <strong>¡Publicación enviada con éxito!</strong>
              <div className="text-neutral-300 pt-0.5">
                Instagram y Facebook procesaron el Reel correctamente. TikTok ya está disponible en tu bandeja de la app.
              </div>
            </div>
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
