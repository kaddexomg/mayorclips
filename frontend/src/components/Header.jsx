import React from "react";
import { Sparkles, Video, Share2, BarChart3, Bot, Clapperboard, Layers, Camera, KeyRound } from "lucide-react";

export default function Header({ currentTab, setTab, pulpoHealth }) {
  const tabs = [
    { id: "dashboard", label: "Dashboard", icon: BarChart3 },
    { id: "new", label: "Nuevo Stream", icon: Video },
    { id: "clips", label: "Clips Virales", icon: Clapperboard },
    { id: "cinema", label: "Cámara IA", icon: Camera },
    { id: "publisher", label: "Publicar", icon: Share2 },
    { id: "accounts", label: "Cuentas", icon: KeyRound },
    { id: "stats", label: "Estadísticas", icon: Layers },
    { id: "studio", label: "Estudio MG", icon: Sparkles },
    { id: "pulpo", label: "El Pulpo", icon: Bot },
  ];

  return (
    <header className="sticky top-0 z-40 border-b border-white/10 bg-abyss/85 backdrop-blur-2xl">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-brand/10 border border-brand/30 shadow-brand-glow">
            <Sparkles className="h-4 w-4 text-brand" />
          </div>
          <span className="font-display font-bold text-base tracking-tight text-text-main flex items-center gap-1.5">
            Mayor<span className="text-brand">Clips</span>
          </span>
        </div>

        <nav className="hidden lg:flex items-center gap-1 bg-ink/70 p-1 rounded-xl border border-white/5">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const active = currentTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setTab(tab.id)}
                className={`btn-tactile flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-medium transition-colors ${
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

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 px-2.5 py-1 rounded-full bg-ink border border-white/10 text-[11px] font-mono">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-brand"></span>
            </span>
            <span className="text-neutral-300">
              {pulpoHealth?.total_keys || 7} Keys
            </span>
          </div>
        </div>
      </div>

      {/* Mobile / Narrow Tablet Nav */}
      <div className="lg:hidden flex items-center gap-1 overflow-x-auto px-4 pb-2.5">
        {tabs.map((tab) => {
          const active = currentTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setTab(tab.id)}
              className={`btn-tactile whitespace-nowrap px-3 py-1 rounded-lg text-[11px] font-medium ${
                active ? "bg-brand text-abyss font-bold" : "bg-ink/60 text-neutral-400"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
    </header>
  );
}
