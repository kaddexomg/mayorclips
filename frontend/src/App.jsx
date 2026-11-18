import React, { useState, useEffect } from "react";
import Header from "./components/Header";
import DashboardView from "./views/DashboardView";
import NewProjectView from "./views/NewProjectView";
import ClipsView from "./views/ClipsView";
import PublisherView from "./views/PublisherView";
import StatsView from "./views/StatsView";
import StudioView from "./views/StudioView";
import PulpoView from "./views/PulpoView";
import { api } from "./api";

export default function App() {
  const [currentTab, setTab] = useState("dashboard");
  const [pulpoHealth, setPulpoHealth] = useState(null);
  const [selectedProject, setSelectedProject] = useState(null);
  const [selectedClipForPublish, setSelectedClipForPublish] = useState(null);

  useEffect(() => {
    async function loadHealth() {
      try {
        const h = await api.getPulpoStatus();
        setPulpoHealth(h);
      } catch (_) {}
    }
    loadHealth();
    const interval = setInterval(loadHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen bg-abyss text-text-main flex flex-col font-sans">
      <Header currentTab={currentTab} setTab={setTab} pulpoHealth={pulpoHealth} />

      <main className="flex-1 max-w-6xl w-full mx-auto px-5 py-8">
        {currentTab === "dashboard" && (
          <DashboardView
            setTab={setTab}
            onSelectProject={(p) => setSelectedProject(p)}
          />
        )}
        {currentTab === "new" && (
          <NewProjectView
            setTab={setTab}
            onProjectCreated={(p) => setSelectedProject(p)}
          />
        )}
        {currentTab === "clips" && (
          <ClipsView
            selectedProject={selectedProject}
            setTab={setTab}
            onSelectClipForPublish={(clip) => setSelectedClipForPublish(clip)}
          />
        )}
        {currentTab === "publisher" && (
          <PublisherView selectedClipForPublish={selectedClipForPublish} />
        )}
        {currentTab === "stats" && <StatsView />}
        {currentTab === "studio" && <StudioView />}
        {currentTab === "pulpo" && <PulpoView />}
      </main>

      <footer className="border-t border-white/5 py-5 text-center text-xs font-mono text-neutral-500 bg-abyss/80">
        MayorClips v1.0.0 · Motor de Clipping con IA y Motion Graphics · Paleta Quanty Clips
      </footer>
    </div>
  );
}
