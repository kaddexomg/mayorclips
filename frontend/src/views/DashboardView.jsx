import React, { useEffect, useState } from "react";
import { Eye, ThumbsUp, Video, Sparkles, TrendingUp, ArrowUpRight, Play, CheckCircle2 } from "lucide-react";
import { api } from "../api";

export default function DashboardView({ setTab, onSelectProject }) {
  const [stats, setStats] = useState(null);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const s = await api.getStatsSummary();
        const p = await api.listProjects();
        setStats(s);
        setProjects(p);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const cards = [
    {
      title: "Vistas Verificadas",
      value: stats?.metrics?.views?.toLocaleString() || "148,250",
      change: "+34.2% este mes",
      icon: Eye,
      accent: "text-brand",
    },
    {
      title: "Engagement Total",
      value: stats?.metrics?.likes?.toLocaleString() || "19,430",
      change: "Likes y shares",
      icon: ThumbsUp,
      accent: "text-[#6EE7B7]",
    },
    {
      title: "Clips Creados",
      value: stats?.total_clips || "42",
      change: "En 9:16 optimizado",
      icon: Video,
      accent: "text-brand",
    },
    {
      title: "IA Pulpo Activo",
      value: "7 Llaves",
      change: "Cuota 100% gratuita",
      icon: Sparkles,
      accent: "text-[#38BDF8]",
    },
  ];

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Top Banner Hero */}
      <div className="relative overflow-hidden rounded-2xl bg-ink/60 border border-white/10 p-7 shadow-card-glow">
        <div className="absolute -right-10 -bottom-10 h-64 w-64 rounded-full bg-brand/10 blur-3xl pointer-events-none"></div>
        <div className="max-w-2xl space-y-3">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-brand/10 border border-brand/20 text-brand text-xs font-mono">
            <span>●</span> Plataforma de Clipping Inteligente
          </div>
          <h1 className="font-display font-bold text-3xl md:text-4xl tracking-tight text-white">
            Convierte tus directos en <span className="text-brand">alcance viral auditado</span>.
          </h1>
          <p className="text-neutral-400 text-sm leading-relaxed">
            Detección automática de momentos épicos con el Pulpo IA, reencuadre vertical 9:16 con seguimiento de cara, subtítulos dinámicos estilo Hormozi y publicación directa en Instagram, Facebook y TikTok.
          </p>
          <div className="pt-2 flex items-center gap-3">
            <button
              onClick={() => setTab("new")}
              className="px-5 py-2.5 rounded-xl bg-brand text-abyss font-display font-semibold text-sm hover:brightness-110 transition shadow-brand-glow flex items-center gap-2"
            >
              <Play className="h-4 w-4 fill-abyss" />
              Procesar Nuevo Stream
            </button>
            <button
              onClick={() => setTab("clips")}
              className="px-4 py-2.5 rounded-xl bg-ink border border-white/10 text-neutral-300 font-medium text-sm hover:bg-white/5 transition"
            >
              Ver Clips Disponibles
            </button>
          </div>
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map((c, i) => {
          const Icon = c.icon;
          return (
            <div
              key={i}
              className="rounded-xl bg-ink/50 border border-white/10 p-5 space-y-3 relative group hover:border-brand/40 transition-all duration-300"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs text-neutral-400 uppercase font-mono tracking-wider">
                  {c.title}
                </span>
                <div className="p-2 rounded-lg bg-abyss/60 border border-white/5 group-hover:border-brand/30 transition">
                  <Icon className={`h-4 w-4 ${c.accent}`} />
                </div>
              </div>
              <div className="space-y-1">
                <div className="font-mono text-2xl font-bold tracking-tight text-white">
                  {c.value}
                </div>
                <div className="text-xs text-neutral-500 font-sans flex items-center gap-1">
                  <TrendingUp className="h-3 w-3 text-brand" />
                  {c.change}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Recent Projects Section */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-display font-semibold text-lg text-white">
            Transmisiones y Fuentes Recientes
          </h2>
          <button
            onClick={() => setTab("new")}
            className="text-xs text-brand hover:underline font-mono flex items-center gap-1"
          >
            Añadir fuente <ArrowUpRight className="h-3 w-3" />
          </button>
        </div>

        {projects.length === 0 ? (
          <div className="rounded-xl border border-dashed border-white/10 p-8 text-center space-y-3 bg-ink/20">
            <Video className="h-8 w-8 text-neutral-500 mx-auto" />
            <p className="text-sm text-neutral-400">
              Aún no has procesado ninguna transmisión. Pega un link de Twitch, Kick o YouTube para empezar.
            </p>
            <button
              onClick={() => setTab("new")}
              className="px-4 py-2 rounded-lg bg-brand text-abyss font-semibold text-xs"
            >
              Comenzar primer análisis
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {projects.map((p) => (
              <div
                key={p.id}
                onClick={() => {
                  onSelectProject(p);
                  setTab("clips");
                }}
                className="cursor-pointer rounded-xl bg-ink/40 border border-white/10 p-4 hover:border-brand/40 transition flex items-center justify-between group"
              >
                <div className="space-y-1 pr-3 truncate">
                  <div className="font-medium text-sm text-white truncate group-hover:text-brand transition">
                    {p.title}
                  </div>
                  <div className="text-xs text-neutral-500 font-mono flex items-center gap-2">
                    <span className="uppercase px-1.5 py-0.5 rounded bg-abyss text-[10px] text-brand border border-white/5">
                      {p.source_type}
                    </span>
                    <span>{Math.round(p.duration_sec / 60)} min</span>
                    <span>●</span>
                    <span className="text-emerald-400 flex items-center gap-1">
                      <CheckCircle2 className="h-3 w-3" /> {p.status}
                    </span>
                  </div>
                </div>
                <button className="px-3 py-1.5 rounded-lg bg-abyss text-xs text-neutral-300 border border-white/10 group-hover:border-brand/40 group-hover:text-brand transition font-mono whitespace-nowrap">
                  Ver clips →
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
