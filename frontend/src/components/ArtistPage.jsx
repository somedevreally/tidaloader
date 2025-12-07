import { h } from "preact";
import { useState, useEffect } from "preact/hooks";
import { api } from "../api/client";
import { downloadManager } from "../utils/downloadManager";
import { useToastStore } from "../stores/toastStore";

export function ArtistPage({ artistId, onBack }) {
  const [loading, setLoading] = useState(true);
  const [artist, setArtist] = useState(null);
  const [topTracks, setTopTracks] = useState([]);
  const [albums, setAlbums] = useState([]);
  const [selectedTracks, setSelectedTracks] = useState(new Set());
  const [selectedAlbums, setSelectedAlbums] = useState(new Set());
  const [error, setError] = useState(null);

  const addToast = useToastStore((state) => state.addToast);

  useEffect(() => {
    loadArtistData();
  }, [artistId]);

  const loadArtistData = async () => {
    setLoading(true);
    setError(null);

    try {
      console.log(`Loading artist data for ID: ${artistId}`);
      const result = await api.get(`/artist/${artistId}`);

      setArtist(result.artist || {});
      setTopTracks(result.tracks || []);
      setAlbums(result.albums || []);

      if (result.tracks) {
        setSelectedTracks(new Set(result.tracks.map((t) => t.id)));
      }

      console.log(
        `Loaded: ${result.tracks?.length || 0} tracks, ${result.albums?.length || 0
        } albums`
      );
    } catch (err) {
      console.error("Failed to load artist:", err);
      setError(err.message);
      addToast(`Failed to load artist: ${err.message}`, "error");
    } finally {
      setLoading(false);
    }
  };

  const toggleTrack = (trackId) => {
    const newSelected = new Set(selectedTracks);
    if (newSelected.has(trackId)) {
      newSelected.delete(trackId);
    } else {
      newSelected.add(trackId);
    }
    setSelectedTracks(newSelected);
  };

  const toggleAlbum = (albumId) => {
    const newSelected = new Set(selectedAlbums);
    if (newSelected.has(albumId)) {
      newSelected.delete(albumId);
    } else {
      newSelected.add(albumId);
    }
    setSelectedAlbums(newSelected);
  };

  const selectAllTracks = () => {
    setSelectedTracks(new Set(topTracks.map((t) => t.id)));
  };

  const deselectAllTracks = () => {
    setSelectedTracks(new Set());
  };

  const selectAllAlbums = () => {
    setSelectedAlbums(new Set(albums.map((a) => a.id)));
  };

  const deselectAllAlbums = () => {
    setSelectedAlbums(new Set());
  };

  const handleDownloadTracks = () => {
    const tracks = topTracks
      .filter((t) => selectedTracks.has(t.id))
      .map((t) => ({
        tidal_id: t.id,
        title: t.title,
        artist: t.artist?.name || artist.name,
        album: t.album?.title,
        cover: t.album?.cover,
        track_number: t.trackNumber,
        tidal_exists: true,
      }));

    downloadManager.addToServerQueue(tracks).then(result => {
      addToast(`Added ${result.added} tracks to download queue`, "success");
    });
  };

  const handleDownloadAlbums = async () => {
    const albumsToDownload = albums.filter((a) => selectedAlbums.has(a.id));

    if (albumsToDownload.length === 0) {
      addToast("No albums selected", "warning");
      return;
    }

    setLoading(true);
    let totalTracks = 0;

    try {
      for (const album of albumsToDownload) {
        console.log(`Fetching tracks for album: ${album.title}`);
        const result = await api.get(`/album/${album.id}/tracks`);

        const tracks = (result.items || []).map((t, index) => ({
          tidal_id: t.id,
          title: t.title,
          artist: t.artist || album.artist?.name || artist.name,
          album: album.title,
          cover: album.cover,
          track_number: t.trackNumber || index + 1,
          tidal_exists: true,
        }));

        const res = await downloadManager.addToServerQueue(tracks);
        totalTracks += res.added;
      }

      addToast(
        `Added ${totalTracks} tracks from ${albumsToDownload.length} albums to queue`,
        "success"
      );
      setSelectedAlbums(new Set());
    } catch (err) {
      addToast(`Failed to fetch album tracks: ${err.message}`, "error");
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadDiscography = async () => {
    if (albums.length === 0) {
      addToast("No albums found for this artist", "warning");
      return;
    }

    setLoading(true);
    let totalTracks = 0;

    try {
      addToast(
        `Downloading entire discography (${albums.length} albums)...`,
        "info"
      );

      for (const album of albums) {
        console.log(`Fetching tracks for album: ${album.title}`);
        const result = await api.get(`/album/${album.id}/tracks`);

        const tracks = (result.items || []).map((t, index) => ({
          tidal_id: t.id,
          title: t.title,
          artist: t.artist || album.artist?.name || artist.name,
          album: album.title,
          cover: album.cover,
          track_number: t.trackNumber || index + 1,
          tidal_exists: true,
        }));

        const res = await downloadManager.addToServerQueue(tracks);
        totalTracks += res.added;

        await new Promise((resolve) => setTimeout(resolve, 200));
      }

      addToast(
        `Added entire discography: ${totalTracks} tracks from ${albums.length} albums`,
        "success"
      );
    } catch (err) {
      addToast(`Failed to fetch discography: ${err.message}`, "error");
    } finally {
      setLoading(false);
    }
  };

  if (loading && !artist) {
    return (
      <div class="space-y-6">
        <button class="btn-surface flex items-center gap-2" onClick={onBack}>
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
              d="M10 19l-7-7m0 0l7-7m-7 7h18"
            />
          </svg>
          Back to Search
        </button>
        <div class="p-12 bg-primary/5 border border-primary/20 rounded-lg text-center">
          <div class="flex items-center justify-center gap-3">
            <svg
              class="animate-spin h-6 w-6 text-primary"
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
            <span class="text-base font-medium text-primary">
              Loading artist...
            </span>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div class="space-y-6">
        <button class="btn-surface flex items-center gap-2" onClick={onBack}>
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
              d="M10 19l-7-7m0 0l7-7m-7 7h18"
            />
          </svg>
          Back to Search
        </button>
        <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
          <p class="text-sm text-red-600">{error}</p>
        </div>
      </div>
    );
  }

  if (!artist) {
    return (
      <div class="space-y-6">
        <button class="btn-surface flex items-center gap-2" onClick={onBack}>
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
              d="M10 19l-7-7m0 0l7-7m-7 7h18"
            />
          </svg>
          Back to Search
        </button>
        <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
          <p class="text-sm text-red-600">Artist not found</p>
        </div>
      </div>
    );
  }

  return (
    <div class="space-y-6">
      <button class="btn-surface flex items-center gap-2" onClick={onBack}>
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
            d="M10 19l-7-7m0 0l7-7m-7 7h18"
          />
        </svg>
        Back to Search
      </button>

      <div class="flex flex-col md:flex-row gap-6 p-6 bg-surface-alt rounded-lg border border-border-light">
        {artist.picture ? (
          <img
            src={api.getCoverUrl(artist.picture, "320")}
            alt={artist.name}
            class="w-48 h-48 rounded-full object-cover shadow-md flex-shrink-0"
          />
        ) : (
          <div class="w-48 h-48 rounded-full bg-gradient-to-br from-primary to-primary-light flex items-center justify-center text-white text-6xl font-bold flex-shrink-0 shadow-md">
            {artist.name?.charAt(0) || "?"}
          </div>
        )}

        <div class="flex-1 flex flex-col justify-center space-y-3">
          <h2 class="text-2xl sm:text-3xl font-bold text-text">
            {artist.name}
          </h2>
          {artist.popularity && (
            <p class="text-base text-text-muted">
              Popularity: {artist.popularity}
            </p>
          )}
          {albums.length > 0 && (
            <button
              class="btn-primary self-start"
              onClick={handleDownloadDiscography}
              disabled={loading}
            >
              Download Entire Discography ({albums.length} albums)
            </button>
          )}
        </div>
      </div>

      {topTracks.length > 0 && (
        <div class="space-y-4">
          <div class="flex items-center justify-between">
            <h3 class="text-xl font-bold text-text">
              Top Tracks ({topTracks.length})
            </h3>
          </div>

          <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-4 bg-surface-alt rounded-lg border border-border-light">
            <div class="flex flex-wrap gap-3">
              <button class="btn-surface text-sm" onClick={selectAllTracks}>
                Select All
              </button>
              <button class="btn-surface text-sm" onClick={deselectAllTracks}>
                Deselect All
              </button>
            </div>
            {selectedTracks.size > 0 && (
              <button class="btn-primary" onClick={handleDownloadTracks}>
                Add {selectedTracks.size} to Queue
              </button>
            )}
          </div>

          <div class="space-y-2 max-h-[600px] overflow-y-auto">
            {topTracks.map((track) => (
              <label
                key={track.id}
                class="flex items-center gap-3 p-3 bg-surface-alt hover:bg-background-alt rounded-lg border border-border-light cursor-pointer transition-all duration-200"
              >
                <input
                  type="checkbox"
                  checked={selectedTracks.has(track.id)}
                  onChange={() => toggleTrack(track.id)}
                  class="w-4 h-4 text-primary focus:ring-primary rounded"
                />
                {track.album?.cover && (
                  <img
                    src={api.getCoverUrl(track.album.cover, "80")}
                    alt={track.title}
                    class="w-12 h-12 rounded object-cover flex-shrink-0"
                  />
                )}
                <div class="flex-1 min-w-0">
                  <p class="text-sm font-medium text-text truncate">
                    {track.title}
                  </p>
                  <p class="text-xs text-text-muted truncate">
                    {track.album?.title || "Unknown Album"}
                    {track.duration && (
                      <span> • {formatDuration(track.duration)}</span>
                    )}
                  </p>
                </div>
                {track.audioQuality && (
                  <span class="px-2 py-1 bg-primary text-white text-xs font-semibold rounded flex-shrink-0">
                    {track.audioQuality}
                  </span>
                )}
              </label>
            ))}
          </div>
        </div>
      )}

      {albums.length > 0 && (
        <div class="space-y-4">
          <div class="flex items-center justify-between">
            <h3 class="text-xl font-bold text-text">
              Albums ({albums.length})
            </h3>
          </div>

          <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-4 bg-surface-alt rounded-lg border border-border-light">
            <div class="flex flex-wrap gap-3">
              <button class="btn-surface text-sm" onClick={selectAllAlbums}>
                Select All
              </button>
              <button class="btn-surface text-sm" onClick={deselectAllAlbums}>
                Deselect All
              </button>
            </div>
            {selectedAlbums.size > 0 && (
              <button
                class="btn-primary"
                onClick={handleDownloadAlbums}
                disabled={loading}
              >
                Add {selectedAlbums.size} Albums to Queue
              </button>
            )}
          </div>

          <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {albums.map((album) => (
              <label
                key={album.id}
                class="card-hover p-3 relative cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={selectedAlbums.has(album.id)}
                  onChange={() => toggleAlbum(album.id)}
                  class="absolute top-5 right-5 w-5 h-5 text-primary focus:ring-primary rounded z-10"
                />
                {album.cover && (
                  <img
                    src={api.getCoverUrl(album.cover, "320")}
                    alt={album.title}
                    class="w-full aspect-square object-cover rounded-lg mb-3"
                  />
                )}
                <div class="space-y-1">
                  <p class="text-sm font-semibold text-text line-clamp-2">
                    {album.title}
                  </p>
                  {album.numberOfTracks && (
                    <p class="text-xs text-text-muted">
                      {album.numberOfTracks} tracks
                    </p>
                  )}
                  {album.releaseDate && (
                    <p class="text-xs text-text-muted">
                      {new Date(album.releaseDate).getFullYear()}
                    </p>
                  )}
                </div>
              </label>
            ))}
          </div>
        </div>
      )}

      {topTracks.length === 0 && albums.length === 0 && (
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
            No tracks or albums found for this artist
          </p>
        </div>
      )}
    </div>
  );
}

function formatDuration(seconds) {
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${minutes}:${secs.toString().padStart(2, "0")}`;
}
