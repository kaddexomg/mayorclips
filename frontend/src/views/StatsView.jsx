import React, { useEffect, useState } from "react";
import { Eye, TrendingUp, BarChart2, Calendar, Award, Instagram, Facebook, Video } from "lucide-react";
import { api } from "../api";

export default function StatsView() {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    async function load() {
      try {
        const s = await api.getStatsSummary();
        setStats(s);
      } catch (e) {
        console.error(e);
      }
    }
    load();
  }, []);

  return (
    <div className="space-y-8 animate-fadeIn">
      <div>
        <h1 className="font-display font-bold text-3xl text-white">
          Estadísticas & Alcance Verificado
        </h1>
        <p className="text-neutral-400 text-sm">
          Monitoreo oficial de reproducciones, retención y crecimiento multi-red conectado mediante APIs oficiales.
        </p>
      </div>

      {/* Main KPI Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <div className="rounded-2xl bg-ink/60 border border-white/10 p-6 space-y-2 relative overflow-hidden">
          <div className="text-xs font-mono text-neutral-400 uppercase tracking-wider">
            Vistas Totales Auditadas
          </div>
          <div className="font-mono text-4xl font-bold text-brand">
            {stats?.metrics?.views ? stats.metrics.views.toLocaleString() : "0"}
          </div>
          <div className="text-xs text-neutral-500 flex items-center gap-1.5 pt-1">
            <span className="text-emerald-400 font-mono font-bold">API Oficial</span> lecturas verificadas
          </div>
        </div>

        <div className="rounded-2xl bg-ink/60 border border-white/10 p-6 space-y-2">
          <div className="text-xs font-mono text-neutral-400 uppercase tracking-wider">
            Reacciones & Compartidos
          </div>
          <div className="font-mono text-4xl font-bold text-white">
            {stats?.metrics?.likes ? stats.metrics.likes.toLocaleString() : "0"}
          </div>
          <div className="text-xs text-neutral-500 flex items-center gap-1.5 pt-1">
            <span className="text-emerald-400 font-mono font-bold">0%</span> engagement
          </div>
        </div>

        <div className="rounded-2xl bg-ink/60 border border-white/10 p-6 space-y-2">
          <div className="text-xs font-mono text-neutral-400 uppercase tracking-wider">
            Horario Recomendado
          </div>
          <div className="font-mono text-2xl font-bold text-[#38BDF8]">
            19:30 - 21:00
          </div>
          <div className="text-xs text-neutral-500 pt-1">
            Ventana de mayor retención de audiencia
          </div>
        </div>
      </div>

      {/* Platform Breakdown */}
      <div className="rounded-2xl bg-ink/60 border border-white/10 p-6 space-y-5">
        <h3 className="font-display font-semibold text-lg text-white">
          Distribución por Plataforma
        </h3>
        
        {(!stats?.metrics?.views || stats.metrics.views === 0) ? (
          <div className="py-8 text-center text-xs font-mono text-neutral-500">
            Aún no hay visualizaciones registradas. Publica tu primer clip en Instagram, Facebook o TikTok para comenzar el monitoreo de métricas.
          </div>
        ) : (
          <div className="space-y-4">
            {/* Instagram */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="flex items-center gap-2 text-pink-400">
                  <Instagram className="h-4 w-4" /> Instagram Reels
                </span>
                <span className="text-white font-bold">{stats?.platforms?.instagram?.views || 0} vistas</span>
              </div>
              <div className="w-full bg-abyss rounded-full h-2.5 overflow-hidden border border-white/5">
                <div className="bg-gradient-to-r from-pink-500 to-purple-500 h-full rounded-full" style={{ width: `${stats?.platforms?.instagram?.views ? 100 : 0}%` }}></div>
              </div>
            </div>

            {/* TikTok */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="flex items-center gap-2 text-brand">
                  <Video className="h-4 w-4" /> TikTok
                </span>
                <span className="text-white font-bold">{stats?.platforms?.tiktok?.views || 0} vistas</span>
              </div>
              <div className="w-full bg-abyss rounded-full h-2.5 overflow-hidden border border-white/5">
                <div className="bg-brand h-full rounded-full" style={{ width: `${stats?.platforms?.tiktok?.views ? 100 : 0}%` }}></div>
              </div>
            </div>

            {/* Facebook */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="flex items-center gap-2 text-blue-400">
                  <Facebook className="h-4 w-4" /> Facebook Page Reels
                </span>
                <span className="text-white font-bold">{stats?.platforms?.facebook?.views || 0} vistas</span>
              </div>
              <div className="w-full bg-abyss rounded-full h-2.5 overflow-hidden border border-white/5">
                <div className="bg-blue-500 h-full rounded-full" style={{ width: `${stats?.platforms?.facebook?.views ? 100 : 0}%` }}></div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
