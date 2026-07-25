import { useFocusEffect } from 'expo-router';
import { StatusBar, StatusBarStyle } from 'expo-status-bar';
import React, { useCallback, useState } from 'react';

/**
 * StatusBar that only applies while its screen is focused.
 * Tab/stack screens stay mounted in the background, so a bare <StatusBar>
 * from an off-screen tab would otherwise win over the visible one.
 */
export function FocusedStatusBar({ style }: { style: StatusBarStyle }) {
  const [focused, setFocused] = useState(false);

  useFocusEffect(
    useCallback(() => {
      setFocused(true);
      return () => setFocused(false);
    }, []),
  );

  return focused ? <StatusBar style={style} /> : null;
}
