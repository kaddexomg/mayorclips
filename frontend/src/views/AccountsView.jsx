import React, { useEffect, useState } from "react";
import { Instagram, Facebook, Video, CheckCircle2, Trash2, KeyRound, ExternalLink, AlertCircle, Loader2, ShieldCheck } from "lucide-react";
import { api } from "../api";

export default function AccountsView() {
  const [accounts, setAccounts] = useState([]);
  const [oauthStatus, setOauthStatus] = useState(null);
  const [metaToken, setMetaToken] = useState("");
  const [tiktokToken, setTiktokToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      const [accs, cfg] = await Promise.all([api.listAccounts(), api.getOAuthConfigStatus()]);
      setAccounts(accs);
      setOauthStatus(cfg);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleMetaOAuth = async () => {
    setError(null);
    try {
      const res = await api.getMetaOAuthStart();
      window.open(res.auth_url, "_blank", "width=640,height=720");
    } catch (err) {
      setError(err.message);
    }
  };

  const handleVerifyMeta = async (e) => {
    e.preventDefault();
    if (!metaToken.trim()) return;
    setLoading(true);
    setError(null);
    setMsg(null);
    try {
      const res = await api.verifyMetaToken(metaToken);
      setMsg(`Conectadas ${res.connected} cuentas reales de Meta (Facebook / Instagram).`);
      setMetaToken("");
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyTikTok = async (e) => {
    e.preventDefault();
    if (!tiktokToken.trim()) return;
    setLoading(true);
    setError(null);
    setMsg(null);
    try {
      const res = await api.verifyTikTokToken(tiktokToken);
      setMsg(`Cuenta de TikTok verificada y conectada: ${res.accounts[0]?.account_name}`);
      setTiktokToken("");
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDisconnect = async (id) => {
    try {
      await api.deleteAccount(id);
      await load();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-fadeIn">
      <div className="text-center space-y-2">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-brand/10 border border-brand/20 text-brand text-xs font-mono">
          <ShieldCheck className="h-3.5 w-3.5" /> Conexiones Oficiales OAuth & Graph API
        </div>
        <h1 className="font-display font-bold text-3xl text-white">
          Cuentas Conectadas
        </h1>
        <p className="text-neutral-400 text-sm max-w-xl mx-auto">
          Vincula tus cuentas reales de Instagram (Empresa/Creador), Páginas de Facebook y TikTok. Todas las publicaciones salen con tus credenciales oficiales.
        </p>
      </div>

      {/* Connected Accounts List */}
      <div className="glass-panel rounded-2xl p-6 space-y-4">
        <h2 className="font-display font-semibold text-base text-white">
          Cuentas Activas ({accounts.length})
        </h2>

        {accounts.length === 0 ? (
          <div className="p-6 rounded-xl border border-dashed border-white/10 text-center text-xs font-mono text-neutral-400">
            No tienes ninguna red social vinculada todavía. Conecta Meta o TikTok abajo.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {accounts.map((acc) => (
              <div
                key={acc.id}
                className="p-4 rounded-xl bg-abyss/80 border border-white/10 flex items-center justify-between"
              >
                <div className="flex items-center gap-3">
                  <div className="p-2.5 rounded-lg bg-brand/10 text-brand">
                    {acc.platform === "instagram" ? (
                      <Instagram className="h-4 w-4 text-pink-400" />
                    ) : acc.platform === "facebook" ? (
                      <Facebook className="h-4 w-4 text-blue-400" />
                    ) : (
                      <Video className="h-4 w-4 text-brand" />
                    )}
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-white">{acc.account_name}</div>
                    <div className="text-[11px] font-mono text-emerald-400 flex items-center gap-1">
                      <CheckCircle2 className="h-3 w-3" /> {acc.platform.toUpperCase()} · ID: {acc.account_id}
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => handleDisconnect(acc.id)}
                  className="btn-tactile p-2 rounded-lg text-neutral-500 hover:text-red-400 hover:bg-red-500/10 transition"
                  title="Desvincular cuenta"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {msg && (
        <div className="rounded-xl bg-emerald-500/10 border border-emerald-500/30 p-4 flex items-center gap-3 text-emerald-400 text-xs font-mono">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          <span>{msg}</span>
        </div>
      )}

      {error && (
        <div className="rounded-xl bg-red-500/10 border border-red-500/30 p-4 flex items-center gap-3 text-red-400 text-xs font-mono">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Connect Meta & TikTok Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Meta Card */}
        <div className="glass-panel rounded-2xl p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-display font-bold text-white flex items-center gap-2">
              <Facebook className="h-5 w-5 text-blue-400" />
              <Instagram className="h-5 w-5 text-pink-400" />
              Meta (FB + IG Reels)
            </h3>
            <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${oauthStatus?.meta_configured ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/10" : "text-amber-300 border-amber-500/30 bg-amber-500/10"}`}>
              {oauthStatus?.meta_configured ? "OAuth Configurado" : "Modo Token Directo"}
            </span>
          </div>

          <p className="text-xs text-neutral-400 leading-relaxed">
            Facebook Reels publica directo desde tu laptop en público. Instagram requiere cuenta Profesional vinculada a tu Página de Facebook y URL pública del VPS.
          </p>

          {oauthStatus?.meta_configured && (
            <button
              onClick={handleMetaOAuth}
              className="btn-tactile w-full py-2.5 rounded-xl bg-blue-600 text-white font-semibold text-xs flex items-center justify-center gap-2"
            >
              <ExternalLink className="h-3.5 w-3.5" /> Iniciar sesión con Facebook / Meta
            </button>
          )}

          <form onSubmit={handleVerifyMeta} className="space-y-3 pt-2 border-t border-white/5">
            <label className="text-[11px] font-mono text-neutral-400 uppercase block">
              Conectar vía Access Token de Meta Graph Explorer
            </label>
            <input
              type="password"
              value={metaToken}
              onChange={(e) => setMetaToken(e.target.value)}
              placeholder="Pega tu User Access Token (EAAG...)"
              className="w-full px-3 py-2 rounded-lg bg-abyss border border-white/10 text-white text-xs font-mono focus:outline-none focus:border-brand"
            />
            <button
              type="submit"
              disabled={loading || !metaToken.trim()}
              className="btn-tactile w-full py-2.5 rounded-xl bg-brand text-abyss font-bold text-xs disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <KeyRound className="h-3.5 w-3.5" />}
              Verificar y Descubrir Páginas e IG
            </button>
          </form>
        </div>

        {/* TikTok Card */}
        <div className="glass-panel rounded-2xl p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-display font-bold text-white flex items-center gap-2">
              <Video className="h-5 w-5 text-brand" />
              TikTok (1-Tap Público)
            </h3>
            <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${oauthStatus?.tiktok_configured ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/10" : "text-amber-300 border-amber-500/30 bg-amber-500/10"}`}>
              {oauthStatus?.tiktok_configured ? "Login Kit Listo" : "Modo Token Directo"}
            </span>
          </div>

          <p className="text-xs text-neutral-400 leading-relaxed">
            Sube el MP4 directo a tu bandeja de TikTok mediante <code className="text-brand">FILE_UPLOAD</code> desde tu laptop. Recibes la notificación en tu móvil y publicas en 1 toque 100% público.
          </p>

          <form onSubmit={handleVerifyTikTok} className="space-y-3 pt-2 border-t border-white/5">
            <label className="text-[11px] font-mono text-neutral-400 uppercase block">
              Conectar vía TikTok OAuth Access Token
            </label>
            <input
              type="password"
              value={tiktokToken}
              onChange={(e) => setTiktokToken(e.target.value)}
              placeholder="Pega tu TikTok Access Token (act....)"
              className="w-full px-3 py-2 rounded-lg bg-abyss border border-white/10 text-white text-xs font-mono focus:outline-none focus:border-brand"
            />
            <button
              type="submit"
              disabled={loading || !tiktokToken.trim()}
              className="btn-tactile w-full py-2.5 rounded-xl bg-brand text-abyss font-bold text-xs disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <KeyRound className="h-3.5 w-3.5" />}
              Verificar y Conectar TikTok
            </button>
          </form>
        </div>
      </div>

      {/* Interactive Setup Guide */}
      <div className="glass-panel rounded-2xl p-6 space-y-5">
        <h3 className="font-display font-bold text-base text-white">
          Guía Rápida Paso a Paso para Vincular tus Cuentas (100% Gratis)
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs text-neutral-300">
          <div className="p-4 rounded-xl bg-abyss/70 border border-white/5 space-y-2">
            <div className="font-bold text-blue-400">1. Facebook e Instagram (Meta)</div>
            <ol className="list-decimal list-inside space-y-1.5 text-[11px] text-neutral-400 leading-relaxed">
              <li>Cambia tu Instagram a cuenta <strong>Profesional (Creador/Empresa)</strong> y vincúlala a una <strong>Página de Facebook</strong>.</li>
              <li>Entra a <a href="https://developers.facebook.com/tools/explorer/" target="_blank" rel="noreferrer" className="text-brand underline">Meta Graph API Explorer</a>.</li>
              <li>Marca los permisos: <code className="text-white">pages_show_list</code>, <code className="text-white">pages_manage_posts</code>, <code className="text-white">instagram_basic</code>, <code className="text-white">instagram_content_publish</code>.</li>
              <li>Genera el Token, pégalo arriba y MayorClips detectará tus páginas y tu IG automáticamente.</li>
            </ol>
          </div>

          <div className="p-4 rounded-xl bg-abyss/70 border border-white/5 space-y-2">
            <div className="font-bold text-brand">2. TikTok (Inbox 1-Tap Público)</div>
            <ol className="list-decimal list-inside space-y-1.5 text-[11px] text-neutral-400 leading-relaxed">
              <li>Crea una app gratuita en <a href="https://developers.tiktok.com/" target="_blank" rel="noreferrer" className="text-brand underline">TikTok for Developers</a>.</li>
              <li>Activa los productos <strong>Login Kit</strong> y <strong>Content Posting API</strong> (permiso <code className="text-white">video.upload</code>).</li>
              <li>Conecta tu cuenta de TikTok como Tester en Sandbox y pega tu <code className="text-white">Access Token</code> arriba.</li>
              <li>Cada clip llegará a tu app para publicarse en público con 1 toque sin bloqueos privados.</li>
            </ol>
          </div>

          <div className="p-4 rounded-xl bg-abyss/70 border border-white/5 space-y-2">
            <div className="font-bold text-red-400">3. YouTube Shorts (Google)</div>
            <ol className="list-decimal list-inside space-y-1.5 text-[11px] text-neutral-400 leading-relaxed">
              <li>Tu proyecto ya tiene el <code className="text-white">GOOGLE_CLIENT_ID</code> conectado en <code className="text-white">.env</code>.</li>
              <li>Activa <strong>YouTube Data API v3</strong> en tu Google Cloud Console de JJ Paper.</li>
              <li>Nota: las apps nuevas en modo prueba suben en privado hasta enviar la verificación gratuita de Google.</li>
            </ol>
          </div>
        </div>
      </div>
    </div>
  );
}
