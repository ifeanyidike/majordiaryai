import { Stack, useRouter, useSegments } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React, { useEffect } from 'react';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { ToastHost } from '@/components';
import { colors } from '@/theme';
import { supabase } from '@/lib/supabase';
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
