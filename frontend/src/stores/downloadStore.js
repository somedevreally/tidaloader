import { create } from "zustand";
import { persist } from "zustand/middleware";
import { api } from "../api/client";

export const useDownloadStore = create(
  persist(
    (set, get) => ({
      queue: [],
      downloading: [],
      completed: [],
      failed: [],
      quality: "LOSSLESS",
      maxConcurrent: 3,
      organizationTemplate: "{Artist}/{Album}/{TrackNumber} - {Title}",
      useMusicBrainz: true,
      runBeets: false,
      embedLyrics: false,
      jellyfinUrl: "",
      jellyfinApiKey: "",
      settingsVersion: 1, // optimistic concurrency version

      // Server queue settings (synced from backend)
      serverQueueSettings: {
        max_concurrent: 3,
        auto_process: true,
        is_processing: false,
        sync_hour: 4,
      },

      // Flag to indicate if we're using server queue
      useServerQueue: true,

      // Pagination state for completed tracks
      completedPagination: {
        items: [],
        total: 0,
        offset: 0,
        limit: 50,
        hasMore: true,
        loading: false,
      },

      addToQueue: (tracks) =>
        set((state) => {
          const existingIds = new Set([
            ...state.queue.map((t) => t.tidal_id),
            ...state.downloading.map((t) => t.tidal_id),
            ...state.completed.map((t) => t.tidal_id),
          ]);

          const newTracks = tracks
            .filter((track) => !existingIds.has(track.tidal_id))
            .map((track) => ({
              ...track,
              id: `${track.tidal_id}-${Date.now()}`,
              status: "queued",
              progress: 0,
              addedAt: Date.now(),
            }));

          if (newTracks.length === 0) {
            console.log("All tracks already in queue");
            return state;
          }

          console.log(
            `Adding ${newTracks.length} new tracks to queue (${tracks.length - newTracks.length
            } duplicates skipped)`
          );

          return {
            queue: [...state.queue, ...newTracks],
          };
        }),

      removeFromQueue: (trackId) =>
        set((state) => ({
          queue: state.queue.filter((t) => t.id !== trackId),
        })),

      startDownload: (trackId) =>
        set((state) => {
          const track = state.queue.find((t) => t.id === trackId);
          if (!track) return state;

          return {
            queue: state.queue.filter((t) => t.id !== trackId),
            downloading: [
              ...state.downloading,
              { ...track, status: "downloading", startedAt: Date.now() },
            ],
          };
        }),

      updateProgress: (trackId, progress) =>
        set((state) => ({
          downloading: state.downloading.map((t) =>
            t.id === trackId ? { ...t, progress } : t
          ),
        })),

      completeDownload: (trackId, filename) =>
        set((state) => {
          const track = state.downloading.find((t) => t.id === trackId);
          if (!track) return state;

          return {
            downloading: state.downloading.filter((t) => t.id !== trackId),
            completed: [
              ...state.completed,
              {
                ...track,
                status: "completed",
                progress: 100,
                completedAt: Date.now(),
                filename,
              },
            ],
          };
        }),

      failDownload: (trackId, error) =>
        set((state) => {
          const track = state.downloading.find((t) => t.id === trackId);
          if (!track) return state;

          return {
            downloading: state.downloading.filter((t) => t.id !== trackId),
            failed: [
              ...state.failed,
              {
                ...track,
                status: "failed",
                error,
                failedAt: Date.now(),
              },
            ],
          };
        }),

      retryFailed: (trackId) =>
        set((state) => {
          const track = state.failed.find((t) => t.id === trackId);
          if (!track) return state;

          return {
            failed: state.failed.filter((t) => t.id !== trackId),
            queue: [
              ...state.queue,
              { ...track, status: "queued", error: undefined, progress: 0 },
            ],
          };
        }),

      clearCompleted: () => set({ completed: [] }),

      clearFailed: () => set({ failed: [] }),

      clearQueue: () => set({ queue: [] }),

      // Load more completed tracks (for infinite scroll)
      loadMoreCompleted: async () => {
        const state = get();
        if (state.completedPagination.loading || !state.completedPagination.hasMore) {
          return;
        }

        set((state) => ({
          completedPagination: { ...state.completedPagination, loading: true },
        }));

        try {
          const result = await api.getCompletedTracks(
            state.completedPagination.limit,
            state.completedPagination.offset
          );

          set((state) => ({
            completedPagination: {
              items: [...state.completedPagination.items, ...result.items],
              total: result.total,
              offset: result.offset + result.items.length,
              limit: result.limit,
              hasMore: result.has_more,
              loading: false,
            },
          }));
        } catch (e) {
          console.error("Failed to load completed tracks:", e);
          set((state) => ({
            completedPagination: { ...state.completedPagination, loading: false },
          }));
        }
      },

      // Clear completed UI (preserves database records)
      clearCompletedUI: () =>
        set({
          completedPagination: {
            items: [],
            total: 0,
            offset: 0,
            limit: 50,
            hasMore: true,
            loading: false,
          },
        }),

      fetchServerSettings: async () => {
        try {
          const res = await fetch('/api/system/settings').then(r => r.json());

          set((state) => ({
            quality: res.quality !== undefined ? res.quality : state.quality,
            organizationTemplate: res.organization_template !== undefined ? res.organization_template : state.organizationTemplate,
            maxConcurrent: res.active_downloads !== undefined ? res.active_downloads : state.maxConcurrent,
            useMusicBrainz: res.use_musicbrainz !== undefined ? res.use_musicbrainz : state.useMusicBrainz,
            runBeets: res.run_beets !== undefined ? res.run_beets : state.runBeets,
            embedLyrics: res.embed_lyrics !== undefined ? res.embed_lyrics : state.embedLyrics,
            jellyfinUrl: res.jellyfin_url !== undefined ? res.jellyfin_url : state.jellyfinUrl,
            jellyfinApiKey: res.jellyfin_api_key !== undefined ? res.jellyfin_api_key : state.jellyfinApiKey,
            settingsVersion: res.version !== undefined ? res.version : state.settingsVersion,

            serverQueueSettings: {
              ...state.serverQueueSettings,
              sync_time: res.sync_time !== undefined ? res.sync_time : state.serverQueueSettings.sync_time
            }
          }));
          return res;
        } catch (e) {
          console.error("Failed to fetch system settings", e);
        }
      },

      updateServerSettings: async (settings) => {
        const currentVersion = get().settingsVersion;
        try {
          const body = { ...settings, version: currentVersion };
          const res = await fetch('/api/system/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
          });

          if (res.status === 409) {
            // Version conflict — another user changed settings
            const errorData = await res.json();
            const current = errorData.detail?.current_settings;
            if (current) {
              // Update local state with server's current values
              set((state) => ({
                quality: current.quality !== undefined ? current.quality : state.quality,
                organizationTemplate: current.organization_template !== undefined ? current.organization_template : state.organizationTemplate,
                maxConcurrent: current.active_downloads !== undefined ? current.active_downloads : state.maxConcurrent,
                useMusicBrainz: current.use_musicbrainz !== undefined ? current.use_musicbrainz : state.useMusicBrainz,
                runBeets: current.run_beets !== undefined ? current.run_beets : state.runBeets,
                embedLyrics: current.embed_lyrics !== undefined ? current.embed_lyrics : state.embedLyrics,
                jellyfinUrl: current.jellyfin_url !== undefined ? current.jellyfin_url : state.jellyfinUrl,
                jellyfinApiKey: current.jellyfin_api_key !== undefined ? current.jellyfin_api_key : state.jellyfinApiKey,
                settingsVersion: current.version !== undefined ? current.version : state.settingsVersion,
                serverQueueSettings: {
                  ...state.serverQueueSettings,
                  sync_time: current.sync_time !== undefined ? current.sync_time : state.serverQueueSettings.sync_time
                }
              }));
            }
            return { conflict: true, current_settings: current };
          }

          if (!res.ok) {
            throw new Error(`Server returned ${res.status}`);
          }

          const data = await res.json();

          // Update local state with confirmed values
          set((state) => ({
            quality: data.quality !== undefined ? data.quality : state.quality,
            organizationTemplate: data.organization_template !== undefined ? data.organization_template : state.organizationTemplate,
            maxConcurrent: data.active_downloads !== undefined ? data.active_downloads : state.maxConcurrent,
            useMusicBrainz: data.use_musicbrainz !== undefined ? data.use_musicbrainz : state.useMusicBrainz,
            runBeets: data.run_beets !== undefined ? data.run_beets : state.runBeets,
            embedLyrics: data.embed_lyrics !== undefined ? data.embed_lyrics : state.embedLyrics,
            jellyfinUrl: data.jellyfin_url !== undefined ? data.jellyfin_url : state.jellyfinUrl,
            jellyfinApiKey: data.jellyfin_api_key !== undefined ? data.jellyfin_api_key : state.jellyfinApiKey,
            settingsVersion: data.version !== undefined ? data.version : state.settingsVersion,
            serverQueueSettings: {
              ...state.serverQueueSettings,
              sync_time: data.sync_time !== undefined ? data.sync_time : state.serverQueueSettings.sync_time
            }
          }));
          return { conflict: false };
        } catch (e) {
          console.error("Failed to update system settings", e);
          throw e;
        }
      },

      retryAllFailed: () =>
        set((state) => {
          const retryTracks = state.failed.map((track) => ({
            ...track,
            status: "queued",
            error: undefined,
            progress: 0,
          }));
          return {
            failed: [],
            queue: [...state.queue, ...retryTracks],
          };
        }),

      setQuality: (quality) => set({ quality }),

      setOrganizationTemplate: (template) => set({ organizationTemplate: template }),
      setUseMusicBrainz: (enabled) => set({ useMusicBrainz: enabled }),
      setRunBeets: (enabled) => set({ runBeets: enabled }),
      setEmbedLyrics: (enabled) => set({ embedLyrics: enabled }),
      setMaxConcurrent: (val) => {
        set({ maxConcurrent: val });
      },

      // Server queue state sync methods
      setServerQueueState: ({ queue, downloading, completed, failed, completedTotal }) =>
        set((state) => ({
          queue: queue !== undefined ? queue : state.queue,
          downloading: downloading !== undefined ? downloading : state.downloading,
          completed: completed !== undefined ? completed : state.completed,
          failed: failed !== undefined ? failed : state.failed,
          completedPagination: {
            ...state.completedPagination,
            total: completedTotal !== undefined ? completedTotal : state.completedPagination.total,
          },
        })),

      setQueueSettings: (settings) =>
        set((state) => ({
          serverQueueSettings: {
            ...state.serverQueueSettings,
            ...settings,
          },
          // Also update maxConcurrent for backwards compatibility
          maxConcurrent: settings.max_concurrent || state.maxConcurrent,
        })),

      setUseServerQueue: (enabled) => set({ useServerQueue: enabled }),

      getStats: () => {
        const state = get();
        return {
          queued: state.queue.length,
          downloading: state.downloading.length,
          completed: state.completed.length,
          failed: state.failed.length,
          total:
            state.queue.length +
            state.downloading.length +
            state.completed.length +
            state.failed.length,
        };
      },

      // State reconciliation methods for backend sync
      syncDownloadState: (trackId, backendStatus, backendData) =>
        set((state) => {
          const track = state.downloading.find((t) => t.id === trackId);
          if (!track) return state;

          const newState = { ...state };

          if (backendStatus === "completed") {
            // Move from downloading to completed
            newState.downloading = state.downloading.filter(
              (t) => t.id !== trackId
            );
            newState.completed = [
              ...state.completed,
              {
                ...track,
                status: "completed",
                progress: 100,
                completedAt: Date.now(),
                filename: backendData.filename || track.title,
              },
            ];
          } else if (backendStatus === "failed") {
            // Move from downloading to failed
            newState.downloading = state.downloading.filter(
              (t) => t.id !== trackId
            );
            newState.failed = [
              ...state.failed,
              {
                ...track,
                status: "failed",
                error: backendData.error || "Download failed",
                failedAt: Date.now(),
              },
            ];
          } else if (backendStatus === "downloading") {
            // Update progress if available
            if (backendData.progress !== undefined) {
              newState.downloading = state.downloading.map((t) =>
                t.id === trackId ? { ...t, progress: backendData.progress } : t
              );
            }
          }

          return newState;
        }),

      bulkReconcileWithBackend: (backendState) =>
        set((state) => {
          const newState = {
            downloading: [],
            completed: [...state.completed],
            failed: [...state.failed],
          };

          // Process each downloading track
          for (const track of state.downloading) {
            const trackId = String(track.tidal_id || track.id);

            // Check backend status
            if (backendState.completed && backendState.completed[trackId]) {
              // Move to completed
              const backendData = backendState.completed[trackId];
              newState.completed.push({
                ...track,
                status: "completed",
                progress: 100,
                completedAt: Date.now(),
                filename: backendData.filename || track.title,
              });
            } else if (backendState.failed && backendState.failed[trackId]) {
              // Move to failed
              const backendData = backendState.failed[trackId];
              newState.failed.push({
                ...track,
                status: "failed",
                error: backendData.error || "Download failed",
                failedAt: Date.now(),
              });
            } else if (backendState.active && backendState.active[trackId]) {
              // Still downloading - update progress
              const backendData = backendState.active[trackId];
              newState.downloading.push({
                ...track,
                progress: backendData.progress || track.progress || 0,
              });
            } else {
              // Not found on backend - mark as failed
              newState.failed.push({
                ...track,
                status: "failed",
                error: "Download not found on server (may have been lost)",
                failedAt: Date.now(),
              });
            }
          }

          return newState;
        }),
    }),
    {
      name: "troi-download-queue",
      partialize: (state) => ({
        queue: state.queue,
        downloading: state.downloading,
        completed: state.completed,
        failed: state.failed,
      }),
    }
  )
);
