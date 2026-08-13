import { Ionicons } from '@expo/vector-icons';
import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, { FadeInUp, FadeOutUp } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { create } from 'zustand';
import { charcoal, colors, radius, red, shadows, spacing, status } from '@/theme';
import { Text } from './Text';

type ToastVariant = 'info' | 'success' | 'error';

interface ToastState {
  message: string | null;
  icon: keyof typeof Ionicons.glyphMap;
  variant: ToastVariant;
  show: (
    message: string,
    icon?: keyof typeof Ionicons.glyphMap,
    variant?: ToastVariant,
  ) => void;
  success: (message: string) => void;
  error: (message: string) => void;
  hide: () => void;
  /** How many native Modals are currently open (see ToastHost). */
  modalDepth: number;
  pushModal: () => void;
  popModal: () => void;
}

export const useToast = create<ToastState>((set) => ({
  message: null,
  icon: 'information-circle',
  variant: 'info',
  show: (message, icon = 'information-circle', variant = 'info') =>
    set({ message, icon, variant }),
  success: (message) => set({ message, icon: 'checkmark-circle', variant: 'success' }),
  error: (message) => set({ message, icon: 'alert-circle', variant: 'error' }),
  hide: () => set({ message: null }),
  modalDepth: 0,
  pushModal: () => set((s) => ({ modalDepth: s.modalDepth + 1 })),
  popModal: () => set((s) => ({ modalDepth: Math.max(0, s.modalDepth - 1) })),
}));

/**
 * Show the toast above an open Modal.
 *
 * React Native renders <Modal> in its own native window, so anything in the
 * root layout — including the toast — is painted UNDERNEATH it, dimmed by the
 * backdrop. No zIndex can fix that; it is a different window. So every modal
 * mounts its own ToastHost, and the root one stands down while any modal is
 * open to avoid rendering the same message twice.
 */
export function useModalToastHost() {
  const { pushModal, popModal } = useToast.getState();
  useEffect(() => {
    pushModal();
    return popModal;
  }, [pushModal, popModal]);
}

const ACCENT: Record<ToastVariant, string> = {
  info: colors.cream.base,
  success: status.pregnant.fg,
  error: red[400],
};

/**
 * Mount once in the root layout, and once inside each Modal with `inModal`.
 * Trigger with useToast.getState().show(...)
 */
export function ToastHost({ inModal = false }: { inModal?: boolean } = {}) {
  const { message, icon, variant, hide, modalDepth } = useToast();
  const insets = useSafeAreaInsets();

  useEffect(() => {
    if (!message) return;
    const t = setTimeout(hide, variant === 'error' ? 3800 : 2600);
    return () => clearTimeout(t);
  }, [message, variant, hide]);

  if (!message) return null;
  // The root host yields while a modal is open; the modal's own host takes over.
  if (!inModal && modalDepth > 0) return null;

  return (
    <Animated.View
      entering={FadeInUp.springify().damping(18)}
      exiting={FadeOutUp}
      style={[styles.toast, { top: (inModal ? 0 : insets.top) + spacing.sm }]}
      pointerEvents="none"
      accessibilityLiveRegion="polite"
    >
      <View style={[styles.accent, { backgroundColor: ACCENT[variant] }]} />
      <Ionicons name={icon} size={20} color={ACCENT[variant]} />
      <Text variant="bodyBold" color={colors.cream.base} style={styles.text}>
        {message}
      </Text>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  toast: {
    position: 'absolute',
    left: spacing.xl,
    right: spacing.xl,
    backgroundColor: charcoal[800],
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md + 2,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    overflow: 'hidden',
    ...shadows.raised,
  },
  accent: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    width: 4,
  },
  text: { flex: 1 },
});


/**
 * Drop inside a <Modal> (conditionally, so it mounts only while open) to make
 * toasts appear above it instead of behind the backdrop.
 */
export function ModalToastHost() {
  useModalToastHost();
  return <ToastHost inModal />;
}
