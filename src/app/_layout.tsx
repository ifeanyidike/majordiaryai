import { Stack, useRouter, useSegments } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import * as Notifications from 'expo-notifications';
import React, { useEffect, useRef } from 'react';
import { AppState } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { ToastHost } from '@/components';
import { colors } from '@/theme';
import { supabase } from '@/lib/supabase';
import { registerForPush } from '@/lib/push';
import { useAppStore } from '@/store/useAppStore';
import { useAuthStore } from '@/store/useAuthStore';

function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const segments = useSegments();
  const { user, loadProfile } = useAuthStore();

  useEffect(() => {
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (_event, session) => {
        if (session) {
          await loadProfile();
        } else {
          useAuthStore.setState({ user: null });
        }
      },
    );
    return () => subscription.unsubscribe();
  }, []);

  // Once someone is signed in (and approved — `user` stays null until an
  // admin activates the account), let this phone be woken for their Alarms
  // and Office Alerts. Re-running on every sign-in is deliberate: the server
  // moves the token to whoever is signed in now.
  useEffect(() => {
    if (user) registerForPush();
  }, [user?.id]);

  // Tapping an alarm opens the feed it belongs to — including when the tap
  // is what launched the app, which is the case that matters on a lock screen.
  //
  // Two traps, both from this hook remembering the last tap:
  //  * On a cold start the sign-in redirect below runs in the same pass and
  //    `replace`s whatever this pushed, so the tap landed on the dashboard.
  //    Waiting until the app is past the login screen lets it land.
  //  * Every later sign-in in the same session would re-open that old feed.
  //    Each tap is handled once, by its notification id.
  const lastTap = Notifications.useLastNotificationResponse();
  const handledTap = useRef<string | null>(null);
  const seg = segments as string[];
  const onLoginScreen = seg.length === 0 || seg[0] === 'register';
  useEffect(() => {
    if (!user || !lastTap || onLoginScreen) return;
    const id = lastTap.notification.request.identifier;
    if (handledTap.current === id) return;
    handledTap.current = id;
    const channel = lastTap.notification.request.content.data?.channel;
    if (channel === 'alarm' || channel === 'office_alert') {
      router.push({ pathname: '/messages/[channel]', params: { channel } });
    }
  }, [lastTap, user?.id, onLoginScreen]);

  // The badges used to be fetched once, when the home screen mounted, so an
  // alarm that arrived while the app was open never showed until he navigated
  // away and back. Refresh when a push lands in the foreground, and whenever
  // the app returns to the front.
  useEffect(() => {
    if (!user) return;
    const refresh = () => useAppStore.getState().fetchUnreadMessageCounts();
    const received = Notifications.addNotificationReceivedListener((n) => {
      refresh();
      // And the feed itself, in case he is looking at it when it lands.
      const channel = n.request.content.data?.channel;
      if (channel === 'alarm' || channel === 'office_alert') {
        useAppStore.getState().fetchMessages(channel);
      }
    });
    const appState = AppState.addEventListener('change', (next) => {
      if (next === 'active') refresh();
    });
    return () => {
      received.remove();
      appState.remove();
    };
  }, [user?.id]);

  useEffect(() => {
    const seg = segments as string[];
    // Auth routes: the login screen ('/') and the register screen.
    const inAuth = seg.length === 0 || seg[0] === 'register';
    if (!user && !inAuth) {
      router.replace('/');
    } else if (user && inAuth) {
      router.replace('/(tabs)/dashboard');
    }
  }, [user, segments]);

  return <>{children}</>;
}

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <StatusBar style="dark" />
        <AuthGuard>
          <Stack
            screenOptions={{
              headerShown: false,
              contentStyle: { backgroundColor: colors.background },
              animation: 'slide_from_right',
            }}
          >
            <Stack.Screen name="index" />
            <Stack.Screen name="(tabs)" options={{ animation: 'fade' }} />
          </Stack>
        </AuthGuard>
        <ToastHost />
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
