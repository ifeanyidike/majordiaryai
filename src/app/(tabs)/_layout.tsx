import { Ionicons } from '@expo/vector-icons';
import { Tabs } from 'expo-router';
import React, { useEffect } from 'react';
import { AppState, ColorValue, Platform } from 'react-native';
import { colors, typography } from '@/theme';
import { useRole } from '@/store/useAuthStore';
import { useAppStore } from '@/store/useAppStore';

type IconName = keyof typeof Ionicons.glyphMap;

const tabIcon =
  (active: IconName, inactive: IconName) =>
  ({ color, focused }: { color: ColorValue; focused: boolean }) => (
    <Ionicons name={focused ? active : inactive} size={24} color={color} />
  );

export default function TabsLayout() {
  const role = useRole();
  const { fetchFarms, fetchCows, fetchVets, fetchWorklist, ensureWorklist, fetchNotifications } =
    useAppStore();

  // Load all core data once when the user enters the tab shell
  useEffect(() => {
    fetchFarms();
    fetchCows();
    fetchVets();
    fetchWorklist();
    fetchNotifications();
  }, []);

  // The worklist is a day's route: an app reopened the next morning must not
  // keep rendering yesterday's farms. ensureWorklist refetches on date change.
  useEffect(() => {
    const sub = AppState.addEventListener('change', (s) => {
      if (s === 'active') ensureWorklist();
    });
    return () => sub.remove();
  }, [ensureWorklist]);

  // Until the role resolves, show only the tabs every role has. Defaulting to
  // 'technician' briefly offered a farm manager the Farms and Tasks tabs.
  const showFarms = role != null && role !== 'farm';
  const showTasks = role === 'technician';

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.tabInactive,
        tabBarLabelStyle: typography.tabLabel,
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          ...Platform.select({ ios: { position: 'absolute' as const }, default: {} }),
        },
      }}
    >
      <Tabs.Screen
        name="dashboard"
        options={{ title: 'Home', tabBarIcon: tabIcon('home', 'home-outline') }}
      />
      <Tabs.Screen
        name="farms"
        options={{
          title: 'Farms',
          tabBarIcon: tabIcon('business', 'business-outline'),
          href: showFarms ? undefined : null,
        }}
      />
      <Tabs.Screen
        name="tasks"
        options={{
          title: 'Tasks',
          tabBarIcon: tabIcon('checkbox', 'checkbox-outline'),
          href: showTasks ? undefined : null,
        }}
      />
      <Tabs.Screen
        name="reports"
        options={{ title: 'Reports', tabBarIcon: tabIcon('bar-chart', 'bar-chart-outline') }}
      />
      <Tabs.Screen
        name="profile"
        options={{ title: 'Profile', tabBarIcon: tabIcon('person', 'person-outline') }}
      />
    </Tabs>
  );
}
