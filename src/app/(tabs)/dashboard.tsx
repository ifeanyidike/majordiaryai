import React from 'react';
import { ActivityIndicator } from 'react-native';
import { Screen } from '@/components';
import { colors, spacing } from '@/theme';
import { AdminDashboard } from '@/features/dashboard/AdminDashboard';
import { FarmDashboard } from '@/features/dashboard/FarmDashboard';
import { TechnicianDashboard } from '@/features/dashboard/TechnicianDashboard';
import { VetDashboard } from '@/features/dashboard/VetDashboard';
import { useRole } from '@/store/useAuthStore';

export default function DashboardScreen() {
  const role = useRole();

  switch (role) {
    case 'admin':
      return <AdminDashboard />;
    case 'farm':
      return <FarmDashboard />;
    case 'vet':
      return <VetDashboard />;
    case 'technician':
      return <TechnicianDashboard />;
    default:
      // Role not resolved yet. This used to fall through to the technician
      // dashboard, so a farm manager or vet saw a flash of somebody else's
      // home screen — and its technician-scoped fetches fired on their behalf.
      return (
        <Screen>
          <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.huge }} />
        </Screen>
      );
  }
}
