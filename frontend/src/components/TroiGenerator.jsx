import { h } from "preact";
import { useState } from "preact/hooks";
import { api } from "../api/client";
import { useDownloadStore } from "../stores/downloadStore";

export function TroiGenerator() {
  const [username, setUsername] = useState("");
  const [loading, setLoading] = useState(false);
  const [tracks, setTracks] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [error, setError] = useState(null);

  const addToQueue = useDownloadStore((state) => state.addToQueue);

  const handleGenerate = async (type) => {
    if (!username.trim()) {
      setError("Please enter a ListenBrainz username");
      return;
    }

    setLoading(true);
    setError(null);
    setTracks([]);
    setSelected(new Set());

    try {
      const result = await api.generateTroiPlaylist(username.trim(), type);
      setTracks(result.tracks);

      const autoSelected = new Set(
        result.tracks.filter((t) => t.tidal_exists).map((t) => t.tidal_id)
      );
      setSelected(autoSelected);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const toggleTrack = (tidalId) => {
    const newSelected = new Set(selected);
    if (newSelected.has(tidalId)) {
      newSelected.delete(tidalId);
    } else {
      newSelected.add(tidalId);
    }
    setSelected(newSelected);
  };

  const toggleAll = () => {
    if (selected.size === tracks.filter((t) => t.tidal_exists).length) {
      setSelected(new Set());
    } else {
      setSelected(
        new Set(tracks.filter((t) => t.tidal_exists).map((t) => t.tidal_id))
      );
    }
  };

  const handleDownload = () => {
    const selectedTracks = tracks.filter((t) => selected.has(t.tidal_id));
    addToQueue(selectedTracks);
    alert(`Added ${selectedTracks.length} tracks to download queue!`);
  };

  return (
    <div class="space-y-6">
      <div class="space-y-4">
        <div class="space-y-2">
          <label
            for="lb-username"
            class="block text-sm font-semibold text-text"
          >
            ListenBrainz Username
          </label>
          <input
            id="lb-username"
            type="text"
            value={username}
            onInput={(e) => setUsername(e.target.value)}
            placeholder="Enter your username"
            disabled={loading}
            class="input-field"
          />
        </div>

        <div class="flex flex-col sm:flex-row gap-3">
          <button
            onClick={() => handleGenerate("daily-jams")}
            disabled={loading || !username.trim()}
            class="btn-primary flex items-center justify-center gap-2 flex-1"
          >
            {loading ? (
              <>
                <svg
                  class="animate-spin h-5 w-5"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    class="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    stroke-width="4"
                  ></circle>
                  <path
                    class="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  ></path>
                </svg>
                Generating...
              </>
            ) : (
              <>
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
                    d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"
                  />
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                Generate Daily Jams
              </>
            )}
          </button>
          <button
            onClick={() => handleGenerate("periodic-jams")}
            disabled={loading || !username.trim()}
            class="btn-secondary flex items-center justify-center gap-2 flex-1"
          >
            {loading ? (
              <>
                <svg
                  class="animate-spin h-5 w-5"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    class="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    stroke-width="4"
                  ></circle>
                  <path
                    class="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  ></path>
                </svg>
                Generating...
              </>
            ) : (
              <>
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
                    d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
                  />
                </svg>
                Generate Periodic Jams
              </>
            )}
          </button>
        </div>
      </div>

      {error && (
        <div class="p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
          <svg
            class="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fill-rule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
              clip-rule="evenodd"
            />
          </svg>
          <p class="text-sm text-red-600">{error}</p>
        </div>
      )}

      {tracks.length > 0 && (
        <div class="space-y-4">
          <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-4 bg-surface-alt rounded-lg border border-border-light">
            <label class="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={
                  selected.size === tracks.filter((t) => t.tidal_exists).length
                }
                onChange={toggleAll}
                class="w-4 h-4 text-primary focus:ring-primary rounded"
              />
              <span class="text-sm font-medium text-text">
                Select All ({tracks.filter((t) => t.tidal_exists).length}{" "}
                available tracks)
              </span>
            </label>
            {selected.size > 0 && (
              <button class="btn-primary" onClick={handleDownload}>
                Add {selected.size} to Queue
              </button>
            )}
          </div>

          <div class="space-y-2 max-h-[600px] overflow-y-auto">
            {tracks.map((track, idx) => (
              <label
                key={idx}
                class={`flex items-center gap-3 p-3 rounded-lg border transition-all duration-200 ${
                  track.tidal_exists
                    ? "bg-surface-alt hover:bg-background-alt border-border-light cursor-pointer"
                    : "bg-red-50 border-red-200 opacity-60 cursor-not-allowed"
                }`}
              >
                <input
                  type="checkbox"
                  checked={selected.has(track.tidal_id)}
                  onChange={() => toggleTrack(track.tidal_id)}
                  disabled={!track.tidal_exists}
                  class="w-4 h-4 text-primary focus:ring-primary rounded disabled:opacity-50"
                />
                <div class="flex-1 min-w-0">
                  <p class="text-sm font-medium text-text truncate">
                    {track.artist} - {track.title}
                  </p>
                  {track.album && (
                    <p class="text-xs text-text-muted truncate">
                      {track.album}
                    </p>
                  )}
                </div>
                {!track.tidal_exists && (
                  <span class="px-2 py-1 bg-red-100 text-red-600 text-xs font-semibold rounded flex-shrink-0">
                    Not Found
                  </span>
                )}
              </label>
            ))}
          </div>

          <div class="p-4 bg-primary/10 rounded-lg border border-primary/20">
            <div class="flex items-center justify-between text-sm">
              <span class="text-text-muted">
                {tracks.filter((t) => t.tidal_exists).length} of {tracks.length}{" "}
                tracks available on Tidal
              </span>
              <span class="font-semibold text-primary">
                {selected.size} selected
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
