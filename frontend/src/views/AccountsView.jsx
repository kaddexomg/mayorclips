import React, { useEffect, useState } from "react";
import {
  Instagram,
  Facebook,
  Video,
  CheckCircle2,
  Trash2,
  KeyRound,
  ExternalLink,
  AlertCircle,
  Loader2,
  ShieldCheck,
  RefreshCw,
  Copy,
  Settings2,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { api } from "../api";

export default function AccountsView() {
  const [accounts, setAccounts] = useState([]);
  const [oauthStatus, setOauthStatus] = useState(null);
  const [metaToken, setMetaToken] = useState("");
  const [tiktokToken, setTiktokToken] = useState("");
  const [showMetaTokenBox, setShowMetaTokenBox] = useState(false);
  const [showTikTokTokenBox, setShowTikTokTokenBox] = useState(false);
  const [showVault, setShowVault] = useState(false);

  // OAuth Developer Credentials Form
  const [metaAppId, setMetaAppId] = useState("");
  const [metaAppSecret, setMetaAppSecret] = useState("");
  const [tiktokKey, setTiktokKey] = useState("");
  const [tiktokSecret, setTiktokSecret] = useState("");

  const [loading, setLoading] = useState(false);
  const [verifyingId, setVerifyingId] = useState(null);
  const [copiedUri, setCopiedUri] = useState("");
  const [msg, setMsg] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      const [accs, cfg] = await Promise.all([api.listAccounts(), api.getOAuthConfigStatus()]);
      setAccounts(accs);
      setOauthStatus(cfg);
      if (!cfg.meta_configured && !cfg.tiktok_configured && accs.length === 0) {
        setShowVault(true);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    load();
    const onOAuthMsg = (ev) => {
      if (ev.data?.type === "mayorclips_oauth") {
        if (ev.data.ok) {
          setMsg(ev.data.title || "Cuenta conectada correctamente.");
          setError(null);
        } else {
          setError(ev.data.title || "No se pudo completar el inicio de sesión OAuth.");
        }
        load();
      }
    };
    window.addEventListener("message", onOAuthMsg);
    return () => window.removeEventListener("message", onOAuthMsg);
  }, []);

  const copyText = (txt, key) => {
    navigator.clipboard.writeText(txt);
    setCopiedUri(key);
    setTimeout(() => setCopiedUri(""), 1800);
  };

  const handleMetaOAuth = async () => {
    setError(null);
    setMsg(null);
    try {
      const res = await api.getMetaOAuthStart();
      window.open(res.auth_url, "mc_meta_oauth", "width=640,height=740");
    } catch (err) {
      setError(err.message);
      setShowVault(true);
    }
  };

  const handleTikTokOAuth = async () => {
    setError(null);
    setMsg(null);
    try {
      const res = await api.getTikTokOAuthStart();
      window.open(res.auth_url, "mc_tiktok_oauth", "width=640,height=740");
    } catch (err) {
      setError(err.message);
      setShowVault(true);
    }
  };

  const handleSaveCredentials = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setMsg(null);
    try {
      const cfg = await api.saveOAuthCredentials({
        meta_app_id: metaAppId || undefined,
        meta_app_secret: metaAppSecret || undefined,
        tiktok_client_key: tiktokKey || undefined,
        tiktok_client_secret: tiktokSecret || undefined,
      });
      setOauthStatus(cfg);
      setMetaAppId("");
      setMetaAppSecret("");
      setTiktokKey("");
      setTiktokSecret("");
      setMsg("Credenciales OAuth guardadas en la bóveda local. Ya puedes usar 'Iniciar Sesión' en 1 clic.");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
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
      setMsg(`Conectadas ${res.connected} cuentas reales de Meta (Facebook + Instagram).`);
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

  const handleTestAccount = async (acc) => {
    setVerifyingId(acc.id);
    setError(null);
    setMsg(null);
    try {
      const res = await api.verifyExistingAccount(acc.id);
      setMsg(
        res.refreshed
          ? `${acc.account_name} (${acc.platform}): token renovado automáticamente.`
          : `${acc.account_name} (${acc.platform}): conexión activa y válida.`
      );
      await load();
    } catch (err) {
      setError(`Error verificando ${acc.account_name}: ${err.message}`);
      await load();
    } finally {
      setVerifyingId(null);
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

  const platStatus = (p) => {
    const found = accounts.filter((a) => a.platform === p);
    if (found.some((a) => a.status === "active")) return { label: "Conectada", active: true };
    if (found.length > 0) return { label: "Expirada", active: false, expired: true };
    return { label: "Pendiente", active: false };
  };

  return (
    <div className="max-w-4xl mx-auto space-y-7 animate-fadeIn">
      <div className="text-center space-y-2">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-brand/10 border border-brand/20 text-brand text-xs font-mono">
          <ShieldCheck className="h-3.5 w-3.5" /> Centro Unificado de Cuentas · Publicación Directa Local
        </div>
        <h1 className="font-display font-bold text-3xl text-white">
          Cuentas Centralizadas
        </h1>
        <p className="text-neutral-400 text-sm max-w-2xl mx-auto">
          Conecta Facebook e Instagram juntos con un solo inicio de sesión de Meta, más TikTok en 1 clic. Las 3 plataformas suben tus MP4 directo desde tu laptop sin necesitar servidor externo.
        </p>
      </div>

      {/* Unified Status Strip */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { key: "facebook", label: "Facebook Reels", icon: Facebook, color: "text-blue-400" },
          { key: "instagram", label: "Instagram Reels", icon: Instagram, color: "text-pink-400" },
          { key: "tiktok", label: "TikTok 1-Tap", icon: Video, color: "text-brand" },
        ].map((item) => {
          const Icon = item.icon;
          const st = platStatus(item.key);
          return (
            <div key={item.key} className="glass-panel rounded-xl p-3.5 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <Icon className={`h-4 w-4 ${item.color}`} />
                <span className="text-xs font-semibold text-white">{item.label}</span>
              </div>
              <span
                className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${
                  st.active
                    ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                    : st.expired
                    ? "bg-red-500/10 text-red-400 border-red-500/30"
                    : "bg-white/5 text-neutral-400 border-white/10"
                }`}
              >
                {st.label}
              </span>
            </div>
          );
        })}
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

      {/* Connected Accounts List */}
      <div className="glass-panel rounded-2xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-display font-semibold text-base text-white">
            Cuentas Vinculadas ({accounts.length})
          </h2>
          <span className="text-[11px] font-mono text-neutral-400">
            Tokens en SQLite local
          </span>
        </div>

        {accounts.length === 0 ? (
          <div className="p-6 rounded-xl border border-dashed border-white/10 text-center text-xs font-mono text-neutral-400">
            No tienes ninguna red social vinculada todavía. Usa los botones de inicio de sesión abajo.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {accounts.map((acc) => (
              <div
                key={acc.id}
                className="p-4 rounded-xl bg-abyss/80 border border-white/10 flex items-center justify-between gap-2"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="p-2.5 rounded-lg bg-brand/10 text-brand shrink-0">
                    {acc.platform === "instagram" ? (
                      <Instagram className="h-4 w-4 text-pink-400" />
                    ) : acc.platform === "facebook" ? (
                      <Facebook className="h-4 w-4 text-blue-400" />
                    ) : (
                      <Video className="h-4 w-4 text-brand" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-white truncate">{acc.account_name}</div>
                    <div className={`text-[11px] font-mono flex items-center gap-1 ${acc.status === "active" ? "text-emerald-400" : "text-red-400"}`}>
                      <CheckCircle2 className="h-3 w-3 shrink-0" />
                      <span className="truncate">
                        {acc.platform.toUpperCase()} · {acc.status === "active" ? (acc.has_refresh ? "Auto-Refresh" : "Activa") : "Expirada"}
                      </span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => handleTestAccount(acc)}
                    disabled={verifyingId === acc.id}
                    className="btn-tactile px-2.5 py-1.5 rounded-lg bg-white/5 hover:bg-brand/15 text-[11px] font-mono text-neutral-300 hover:text-brand flex items-center gap-1 transition"
                    title="Probar y refrescar conexión"
                  >
                    <RefreshCw className={`h-3 w-3 ${verifyingId === acc.id ? "animate-spin" : ""}`} />
                    Probar
                  </button>
                  <button
                    onClick={() => handleDisconnect(acc.id)}
                    className="btn-tactile p-2 rounded-lg text-neutral-500 hover:text-red-400 hover:bg-red-500/10 transition"
                    title="Desvincular cuenta"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Centralized Login Cards: Meta (2-in-1) & TikTok */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Meta Card */}
        <div className="glass-panel rounded-2xl p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-display font-bold text-white flex items-center gap-2">
              <Facebook className="h-5 w-5 text-blue-400" />
              <Instagram className="h-5 w-5 text-pink-400" />
              Meta (FB + IG 2-en-1)
            </h3>
            <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${oauthStatus?.meta_configured ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/10" : "text-amber-300 border-amber-500/30 bg-amber-500/10"}`}>
              {oauthStatus?.meta_configured ? `OAuth Listo (${oauthStatus.meta_app_id_hint})` : "Falta App ID"}
            </span>
          </div>

          <p className="text-xs text-neutral-400 leading-relaxed">
            Un solo login conecta tu <strong>Página de Facebook</strong> y el <strong>Instagram Profesional</strong> vinculado a ella. Sube Reels directo desde tu laptop en binario (sin necesitar VPS).
          </p>

          <button
            onClick={handleMetaOAuth}
            className="btn-tactile w-full py-3 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs flex items-center justify-center gap-2"
          >
            <ExternalLink className="h-3.5 w-3.5" /> Iniciar sesión con Facebook + Instagram
          </button>

          <button
            type="button"
            onClick={() => setShowMetaTokenBox(!showMetaTokenBox)}
            className="w-full flex items-center justify-between text-[11px] font-mono text-neutral-400 hover:text-white pt-1"
          >
            <span>Opción alterna: pegar Access Token manual</span>
            {showMetaTokenBox ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>

          {showMetaTokenBox && (
            <form onSubmit={handleVerifyMeta} className="space-y-2.5 pt-2 border-t border-white/5">
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
                className="btn-tactile w-full py-2 rounded-xl bg-brand text-abyss font-bold text-xs disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <KeyRound className="h-3.5 w-3.5" />}
                Conectar Token Meta
              </button>
            </form>
          )}
        </div>

        {/* TikTok Card */}
        <div className="glass-panel rounded-2xl p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-display font-bold text-white flex items-center gap-2">
              <Video className="h-5 w-5 text-brand" />
              TikTok (1-Tap Público)
            </h3>
            <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${oauthStatus?.tiktok_configured ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/10" : "text-amber-300 border-amber-500/30 bg-amber-500/10"}`}>
              {oauthStatus?.tiktok_configured ? `Login Kit (${oauthStatus.tiktok_key_hint})` : "Falta Client Key"}
            </span>
          </div>

          <p className="text-xs text-neutral-400 leading-relaxed">
            Inicia sesión con TikTok Login Kit Desktop (auto-refresca sesión). Envía el MP4 a tu bandeja oficial y publicas en 1 toque 100% público desde tu móvil.
          </p>

          <button
            onClick={handleTikTokOAuth}
            className="btn-tactile w-full py-3 rounded-xl bg-brand text-abyss font-bold text-xs flex items-center justify-center gap-2 shadow-brand-glow"
          >
            <ExternalLink className="h-3.5 w-3.5" /> Iniciar sesión con TikTok
          </button>

          <button
            type="button"
            onClick={() => setShowTikTokTokenBox(!showTikTokTokenBox)}
            className="w-full flex items-center justify-between text-[11px] font-mono text-neutral-400 hover:text-white pt-1"
          >
            <span>Opción alterna: pegar Access Token manual</span>
            {showTikTokTokenBox ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>

          {showTikTokTokenBox && (
            <form onSubmit={handleVerifyTikTok} className="space-y-2.5 pt-2 border-t border-white/5">
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
                className="btn-tactile w-full py-2 rounded-xl bg-ink border border-brand/40 text-brand font-bold text-xs disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <KeyRound className="h-3.5 w-3.5" />}
                Conectar Token TikTok
              </button>
            </form>
          )}
        </div>
      </div>

      {/* Centralized Developer Credentials Vault */}
      <div className="glass-panel rounded-2xl p-6 space-y-4">
        <button
          type="button"
          onClick={() => setShowVault(!showVault)}
          className="w-full flex items-center justify-between text-left"
        >
          <div className="flex items-center gap-2.5">
            <Settings2 className="h-4 w-4 text-brand" />
            <div>
              <h3 className="font-display font-bold text-sm text-white">
                Bóveda Central de Credenciales OAuth (1 sola vez, sin editar .env)
              </h3>
              <p className="text-[11px] text-neutral-400">
                Guarda aquí tus llaves gratuitas de Meta for Developers y TikTok Developers para habilitar el login en 1 clic.
              </p>
            </div>
          </div>
          {showVault ? <ChevronUp className="h-4 w-4 text-neutral-400" /> : <ChevronDown className="h-4 w-4 text-neutral-400" />}
        </button>

        {showVault && (
          <form onSubmit={handleSaveCredentials} className="space-y-5 pt-4 border-t border-white/10">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-4 rounded-xl bg-abyss/70 border border-white/5 space-y-3">
                <div className="text-xs font-bold text-blue-400">Meta App (Facebook + Instagram)</div>
                <input
                  type="text"
                  value={metaAppId}
                  onChange={(e) => setMetaAppId(e.target.value)}
                  placeholder={oauthStatus?.meta_configured ? `App ID actual (${oauthStatus.meta_app_id_hint})` : "Meta App ID"}
                  className="w-full px-3 py-2 rounded-lg bg-ink border border-white/10 text-white text-xs font-mono focus:outline-none focus:border-brand"
                />
                <input
                  type="password"
                  value={metaAppSecret}
                  onChange={(e) => setMetaAppSecret(e.target.value)}
                  placeholder={oauthStatus?.meta_configured ? "App Secret guardado (opcional cambiar)" : "Meta App Secret"}
                  className="w-full px-3 py-2 rounded-lg bg-ink border border-white/10 text-white text-xs font-mono focus:outline-none focus:border-brand"
                />
                {oauthStatus?.meta_redirect_uri && (
                  <div className="flex items-center justify-between gap-2 p-2 rounded-lg bg-ink/80 border border-white/5 text-[10px] font-mono text-neutral-400">
                    <span className="truncate">Callback: {oauthStatus.meta_redirect_uri}</span>
                    <button
                      type="button"
                      onClick={() => copyText(oauthStatus.meta_redirect_uri, "meta")}
                      className="text-brand shrink-0 flex items-center gap-1"
                    >
                      <Copy className="h-3 w-3" /> {copiedUri === "meta" ? "Copiado" : "Copiar"}
                    </button>
                  </div>
                )}
              </div>

              <div className="p-4 rounded-xl bg-abyss/70 border border-white/5 space-y-3">
                <div className="text-xs font-bold text-brand">TikTok Developer App</div>
                <input
                  type="text"
                  value={tiktokKey}
                  onChange={(e) => setTiktokKey(e.target.value)}
                  placeholder={oauthStatus?.tiktok_configured ? `Client Key actual (${oauthStatus.tiktok_key_hint})` : "TikTok Client Key"}
                  className="w-full px-3 py-2 rounded-lg bg-ink border border-white/10 text-white text-xs font-mono focus:outline-none focus:border-brand"
                />
                <input
                  type="password"
                  value={tiktokSecret}
                  onChange={(e) => setTiktokSecret(e.target.value)}
                  placeholder={oauthStatus?.tiktok_configured ? "Client Secret guardado (opcional cambiar)" : "TikTok Client Secret"}
                  className="w-full px-3 py-2 rounded-lg bg-ink border border-white/10 text-white text-xs font-mono focus:outline-none focus:border-brand"
                />
                {oauthStatus?.tiktok_redirect_uri && (
                  <div className="flex items-center justify-between gap-2 p-2 rounded-lg bg-ink/80 border border-white/5 text-[10px] font-mono text-neutral-400">
                    <span className="truncate">Callback: {oauthStatus.tiktok_redirect_uri}</span>
                    <button
                      type="button"
                      onClick={() => copyText(oauthStatus.tiktok_redirect_uri, "tiktok")}
                      className="text-brand shrink-0 flex items-center gap-1"
                    >
                      <Copy className="h-3 w-3" /> {copiedUri === "tiktok" ? "Copiado" : "Copiar"}
                    </button>
                  </div>
                )}
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-tactile px-6 py-2.5 rounded-xl bg-brand text-abyss font-bold text-xs flex items-center gap-2"
            >
              {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
              Guardar Credenciales Centralizadas
            </button>
          </form>
        )}
      </div>

      {/* Step-by-step Factible Setup Guide */}
      <div className="glass-panel rounded-2xl p-6 space-y-4">
        <h3 className="font-display font-bold text-base text-white">
          Ruta Más Factible y Rápida (FB + IG + TikTok)
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs text-neutral-300">
          <div className="p-4 rounded-xl bg-abyss/70 border border-white/5 space-y-2">
            <div className="font-bold text-blue-400">1. Facebook + Instagram en 1 solo Login</div>
            <ol className="list-decimal list-inside space-y-1.5 text-[11px] text-neutral-400 leading-relaxed">
              <li>Pasa tu Instagram a cuenta <strong>Profesional (Creador o Empresa)</strong> y vincúlala a tu <strong>Página de Facebook</strong> desde la app de IG/Meta.</li>
              <li>En <a href="https://developers.facebook.com/" target="_blank" rel="noreferrer" className="text-brand underline">Meta for Developers</a> crea una app gratis, agrega <strong>Facebook Login</strong> y déjala en <strong>Modo Desarrollo</strong> (permite <code className="text-white">localhost</code>/<code className="text-white">127.0.0.1</code> sin HTTPS).</li>
              <li>Copia tu <strong>App ID</strong> y <strong>App Secret</strong> arriba en la Bóveda Central y pulsa <strong>Iniciar sesión con Facebook + Instagram</strong> (tokens de página permanentes).</li>
            </ol>
          </div>

          <div className="p-4 rounded-xl bg-abyss/70 border border-white/5 space-y-2">
            <div className="font-bold text-brand">2. TikTok (Desktop OAuth + Bandeja 1-Tap)</div>
            <ol className="list-decimal list-inside space-y-1.5 text-[11px] text-neutral-400 leading-relaxed">
              <li>En <a href="https://developers.tiktok.com/" target="_blank" rel="noreferrer" className="text-brand underline">TikTok for Developers</a> crea una app con plataforma <strong>Desktop</strong>.</li>
              <li>Activa <strong>Login Kit</strong> + <strong>Content Posting API</strong> (<code className="text-white">video.upload</code>) y pega la URL de Callback mostrada en la Bóveda.</li>
              <li>Agrega tu cuenta en Sandbox (o producción tras revisión), guarda Key/Secret arriba y pulsa <strong>Iniciar sesión con TikTok</strong>.</li>
            </ol>
          </div>
        </div>
      </div>
    </div>
  );
}
