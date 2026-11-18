import React from "react";
import { Sparkles, Video, Share2, BarChart3, Bot, Clapperboard, Layers } from "lucide-react";

export default function Header({ currentTab, setTab, pulpoHealth }) {
  const tabs = [
    { id: "dashboard", label: "Dashboard", icon: BarChart3 },
    { id: "new", label: "Nuevo Proyecto", icon: Video },
    { id: "clips", label: "Clips Virales", icon: Clapperboard },
    { id: "publisher", label: "Publicar", icon: Share2 },
    { id: "stats", label: "Estadísticas", icon: Layers },
    { id: "studio", label: "Estudio MG", icon: Sparkles },
    { id: "pulpo", label: "El Pulpo IA", icon: Bot },
  ];

  return (
    <header className="sticky top-0 z-40 border-b border-white/10 bg-abyss/85 backdrop-blur-xl">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3.5">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand/10 border border-brand/30 shadow-brand-glow">
            <Sparkles className="h-5 w-5 text-brand" />
          </div>
          <div>
            <span className="font-display font-bold text-lg tracking-tight text-text-main flex items-center gap-1.5">
              Mayor<span className="text-brand">Clips</span>
              <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-brand/10 text-brand border border-brand/20">
                PRO
              </span>
            </span>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav className="hidden md:flex items-center gap-1 bg-ink/70 p-1 rounded-xl border border-white/5">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const active = currentTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setTab(tab.id)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  active
                    ? "bg-brand text-abyss font-semibold shadow-sm"
                    : "text-neutral-400 hover:text-white hover:bg-white/5"
                }`}
              >
                <Icon className={`h-3.5 w-3.5 ${active ? "text-abyss" : "text-brand"}`} />
                {tab.label}
              </button>
            );
          })}
        </nav>

        {/* Pulpo Health Badge */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 px-2.5 py-1 rounded-full bg-ink border border-white/10 text-xs font-mono">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-brand"></span>
            </span>
            <span className="text-neutral-300">
              {pulpoHealth?.total_keys || 7} Keys Activas
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}
