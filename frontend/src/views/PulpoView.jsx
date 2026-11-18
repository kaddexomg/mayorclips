import React, { useEffect, useState } from "react";
import { Bot, Sparkles, CheckCircle2, ShieldCheck, Activity, RefreshCw } from "lucide-react";
import { api } from "../api";

export default function PulpoView() {
  const [pulpo, setPulpo] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadStatus = async () => {
    try {
      setLoading(true);
      const data = await api.getPulpoStatus();
      setPulpo(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-fadeIn">
      <div className="flex items-center justify-between">
        <div>
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-brand/10 border border-brand/20 text-brand text-xs font-mono mb-2">
            <Bot className="h-3.5 w-3.5" /> Router IA Multi-API Soberano
          </div>
          <h1 className="font-display font-bold text-3xl text-white">
            El Pulpo (Pool de 7 API Keys)
          </h1>
          <p className="text-neutral-400 text-sm">
            Monitoreo en tiempo real del balanceo, rotación automática ante cuotas y protección de tokens.
          </p>
        </div>
        <button
          onClick={loadStatus}
          className="p-2.5 rounded-xl bg-ink border border-white/10 text-neutral-300 hover:text-brand hover:border-brand/40 transition"
          title="Refrescar estado"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin text-brand" : ""}`} />
        </button>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-xl bg-ink/60 border border-white/10 p-5 space-y-1">
          <div className="text-xs font-mono text-neutral-400 uppercase">Pool Soberano</div>
          <div className="font-mono text-2xl font-bold text-brand">
            {pulpo?.total_keys || 7} API Keys
          </div>
          <div className="text-xs text-neutral-500">Google Gemini AI Studio</div>
        </div>

        <div className="rounded-xl bg-ink/60 border border-white/10 p-5 space-y-1">
          <div className="text-xs font-mono text-neutral-400 uppercase">Modelos Activos</div>
          <div className="font-mono text-sm font-bold text-white truncate">
            gemini-3-flash-preview
          </div>
          <div className="text-xs text-emerald-400 font-mono">Fallback: 3.1-flash-lite</div>
        </div>

        <div className="rounded-xl bg-ink/60 border border-white/10 p-5 space-y-1">
          <div className="text-xs font-mono text-neutral-400 uppercase">Peticiones Totales</div>
          <div className="font-mono text-2xl font-bold text-[#38BDF8]">
            {pulpo?.total_api_calls || 0}
          </div>
          <div className="text-xs text-neutral-500 font-mono">
            {pulpo?.total_tokens_used?.toLocaleString() || 0} tokens
          </div>
        </div>
      </div>

      {/* Keys Table */}
      <div className="rounded-2xl bg-ink/70 border border-white/10 overflow-hidden shadow-card-glow">
        <div className="p-4 border-b border-white/5 font-display font-semibold text-sm text-white">
          Estado Individual de las Llaves
        </div>
        <div className="divide-y divide-white/5">
          {pulpo?.keys?.map((k, idx) => (
            <div key={idx} className="p-4 flex items-center justify-between hover:bg-white/[0.02] transition">
              <div className="flex items-center gap-3">
                <div className="font-mono text-xs text-neutral-500">#{idx + 1}</div>
                <div>
                  <div className="font-mono text-xs font-bold text-white">
                    {k.key_prefix}
                  </div>
                  <div className="text-[11px] text-neutral-500">
                    {k.calls} llamadas · {k.tokens} tokens
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-3">
                {k.errors > 0 && (
                  <span className="text-[11px] font-mono text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded border border-amber-400/20">
                    {k.errors} 429
                  </span>
                )}
                <span
                  className={`px-2.5 py-0.5 rounded-full text-[11px] font-mono font-semibold uppercase flex items-center gap-1.5 ${
                    k.status === "active"
                      ? "bg-brand/10 text-brand border border-brand/30"
                      : "bg-red-500/10 text-red-400 border border-red-500/30"
                  }`}
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-brand"></span>
                  {k.status}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
