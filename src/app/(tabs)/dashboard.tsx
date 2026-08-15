import React from 'react';
import { View } from 'react-native';
import { Screen, SkeletonList, SkeletonStats } from '@/components';
import { spacing } from '@/theme';
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
          <View style={{ gap: spacing.xl, marginTop: spacing.xl }}>
            <SkeletonStats />
            <SkeletonList count={3} variant="card" />
          </View>
        </Screen>
      );
  }
}
