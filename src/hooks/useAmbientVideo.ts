import { useFocusEffect } from 'expo-router';
import { useVideoPlayer } from 'expo-video';
import { useCallback, useEffect, useState } from 'react';

/**
 * Looping, muted ambient background video for the auth screens.
 * - Pauses when the screen loses focus (login stays mounted under register,
 *   so without this two decoders run at once).
 * - Reports failure so the caller can fall back to the poster image.
 */
export function useAmbientVideo(source: number) {
  const [failed, setFailed] = useState(false);

  const player = useVideoPlayer(source, (p) => {
    p.loop = true;
    p.muted = true;
  });

  useEffect(() => {
    const sub = player.addListener('statusChange', ({ status }) => {
      if (status === 'error') setFailed(true);
    });
    return () => sub.remove();
  }, [player]);

  useFocusEffect(
    useCallback(() => {
      if (!failed) {
        try { player.play(); } catch { /* player may be released */ }
      }
      return () => {
        try { player.pause(); } catch { /* player may be released */ }
      };
    }, [player, failed]),
  );

  return { player, videoFailed: failed };
}
