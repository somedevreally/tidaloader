import { h } from "preact";
import { useState } from "preact/hooks";
import { useDownloadStore } from "../stores/downloadStore";
import { downloadManager } from "../utils/downloadManager";

export function DownloadQueue() {
  const queue = useDownloadStore((state) => state.queue);
  const downloading = useDownloadStore((state) => state.downloading);
  const completed = useDownloadStore((state) => state.completed);
  const failed = useDownloadStore((state) => state.failed);
  const removeFromQueue = useDownloadStore((state) => state.removeFromQueue);
  const retryFailed = useDownloadStore((state) => state.retryFailed);
  const clearCompleted = useDownloadStore((state) => state.clearCompleted);
  const clearFailed = useDownloadStore((state) => state.clearFailed);

  const [isRunning, setIsRunning] = useState(false);

  const totalInQueue = queue.length + downloading.length;

  const handleStart = async () => {
    setIsRunning(true);
    downloadManager.start().catch((err) => {
      console.error("Download manager error:", err);
      setIsRunning(false);
    });
  };

  const handleStop = () => {
    downloadManager.stop();
    setIsRunning(false);
  };

  return (
    <div class="card p-6">
      <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 mb-6">
        <h2 class="text-xl font-bold text-text">Download Queue</h2>

        <div class="flex flex-wrap gap-4 text-sm text-text-muted">
          <div class="flex items-center gap-2">
            <div class="w-2 h-2 rounded-full bg-secondary"></div>
            <span>Queued: {queue.length}</span>
          </div>
          <div class="flex items-center gap-2">
            <div class="w-2 h-2 rounded-full bg-primary animate-pulse"></div>
            <span>Downloading: {downloading.length}</span>
          </div>
          <div class="flex items-center gap-2">
            <div class="w-2 h-2 rounded-full bg-primary-dark"></div>
            <span>Completed: {completed.length}</span>
          </div>
          {failed.length > 0 && (
            <div class="flex items-center gap-2">
              <div class="w-2 h-2 rounded-full bg-red-400"></div>
              <span>Failed: {failed.length}</span>
            </div>
          )}
        </div>

        <div class="flex gap-2">
          {!isRunning ? (
            <button
              onClick={handleStart}
              disabled={totalInQueue === 0}
              class="btn-primary flex items-center gap-2"
            >
              <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                <path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
              </svg>
              Start Downloads
            </button>
          ) : (
            <button
              onClick={handleStop}
              class="bg-red-400 hover:bg-red-500 text-white font-medium px-4 py-2 rounded-lg transition-colors duration-200 flex items-center gap-2"
            >
              <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fill-rule="evenodd"
                  d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zM7 8a1 1 0 012 0v4a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v4a1 1 0 102 0V8a1 1 0 00-1-1z"
                  clip-rule="evenodd"
                />
              </svg>
              Stop Downloads
            </button>
          )}
        </div>
      </div>

      {queue.length > 0 && (
        <div class="mb-6">
          <h3 class="text-sm font-semibold text-text-muted mb-3">
            Queued ({queue.length})
          </h3>
          <div class="space-y-2 max-h-64 overflow-y-auto">
            {queue.map((track) => (
              <div
                key={track.id}
                class="flex items-center justify-between p-3 bg-surface-alt rounded-lg border border-border-light"
              >
                <div class="flex-1 min-w-0">
                  <p class="text-sm font-medium text-text truncate">
                    {track.artist} - {track.title}
                  </p>
                </div>
                <button
                  class="ml-3 p-2 hover:bg-red-50 rounded-lg transition-colors duration-200 flex-shrink-0"
                  onClick={() => removeFromQueue(track.id)}
                  title="Remove from queue"
                >
                  <svg
                    class="w-4 h-4 text-red-400"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      stroke-width="2"
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                    />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {downloading.length > 0 && (
        <div class="mb-6">
          <h3 class="text-sm font-semibold text-text-muted mb-3">
            Downloading ({downloading.length})
          </h3>
          <div class="space-y-2">
            {downloading.map((track) => (
              <div
                key={track.id}
                class="p-3 bg-primary/5 rounded-lg border border-primary/20"
              >
                <div class="flex items-center justify-between mb-2">
                  <p class="text-sm font-medium text-text truncate">
                    {track.artist} - {track.title}
                  </p>
                  <span class="text-xs font-semibold text-primary ml-3">
                    {track.progress || 0}%
                  </span>
                </div>
                <div class="w-full bg-border rounded-full h-2 overflow-hidden">
                  <div
                    class="h-full bg-gradient-to-r from-primary to-primary-light transition-all duration-300 ease-out"
                    style={{ width: `${track.progress || 0}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {failed.length > 0 && (
        <div class="mb-6">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-semibold text-text-muted">
              Failed ({failed.length})
            </h3>
            <button
              class="text-xs text-red-400 hover:text-red-500 font-medium"
              onClick={clearFailed}
            >
              Clear All
            </button>
          </div>
          <div class="space-y-2 max-h-64 overflow-y-auto">
            {failed.map((track) => (
              <div
                key={track.id}
                class="p-3 bg-red-50 rounded-lg border border-red-200"
              >
                <div class="flex items-start justify-between">
                  <div class="flex-1 min-w-0">
                    <p class="text-sm font-medium text-text truncate">
                      {track.artist} - {track.title}
                    </p>
                    <p class="text-xs text-red-400 mt-1">{track.error}</p>
                  </div>
                  <button
                    class="ml-3 p-2 hover:bg-red-100 rounded-lg transition-colors duration-200 flex-shrink-0"
                    onClick={() => retryFailed(track.id)}
                    title="Retry download"
                  >
                    <svg
                      class="w-4 h-4 text-primary"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        stroke-width="2"
                        d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                      />
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {completed.length > 0 && (
        <div class="p-4 bg-primary/10 rounded-lg border border-primary/20">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <svg
                class="w-5 h-5 text-primary"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <span class="text-sm font-semibold text-primary">
                Completed: {completed.length} tracks
              </span>
            </div>
            <button
              class="text-xs text-text-muted hover:text-text font-medium"
              onClick={clearCompleted}
            >
              Clear
            </button>
          </div>
        </div>
      )}

      {totalInQueue === 0 && completed.length === 0 && failed.length === 0 && (
        <div class="text-center py-12">
          <svg
            class="w-16 h-16 mx-auto text-border mb-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"
            />
          </svg>
          <p class="text-text-muted">
            No tracks in queue. Add some tracks to get started!
          </p>
        </div>
      )}
    </div>
  );
}
