import { h } from "preact";
import { useState } from "preact/hooks";
import { SearchBar } from "./components/SearchBar";
import { TroiGenerator } from "./components/TroiGenerator";
import { DownloadQueue } from "./components/DownloadQueue";
import { QualitySelector } from "./components/QualitySelector";

export function App() {
  const [activeTab, setActiveTab] = useState("search");
  const [showSettings, setShowSettings] = useState(false);

  return (
    <div class="min-h-screen bg-background">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <header class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
          <h1 class="text-2xl sm:text-3xl font-bold text-text">
            Troi Tidal Downloader
          </h1>
          <button
            class="btn-surface flex items-center gap-2 self-start sm:self-auto"
            onClick={() => setShowSettings(!showSettings)}
          >
            <svg
              class="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
              />
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
              />
            </svg>
            Settings
          </button>
        </header>

        {showSettings && (
          <div class="card p-6 mb-6">
            <QualitySelector />
          </div>
        )}

        <nav class="flex gap-2 mb-6 border-b border-border pb-0">
          <button
            class={`px-6 py-3 font-medium rounded-t-lg transition-all duration-200 ${
              activeTab === "search"
                ? "bg-surface text-primary border-b-2 border-primary -mb-px"
                : "text-text-muted hover:text-text hover:bg-surface-alt"
            }`}
            onClick={() => setActiveTab("search")}
          >
            Custom Search
          </button>
          <button
            class={`px-6 py-3 font-medium rounded-t-lg transition-all duration-200 ${
              activeTab === "troi"
                ? "bg-surface text-primary border-b-2 border-primary -mb-px"
                : "text-text-muted hover:text-text hover:bg-surface-alt"
            }`}
            onClick={() => setActiveTab("troi")}
          >
            Troi Playlist
          </button>
        </nav>

        <main class="card p-6 mb-6 min-h-[400px]">
          {activeTab === "search" && <SearchBar />}
          {activeTab === "troi" && <TroiGenerator />}
        </main>

        <footer>
          <DownloadQueue />
        </footer>
      </div>
    </div>
  );
}
