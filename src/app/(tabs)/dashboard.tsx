import React from 'react';
import { AdminDashboard } from '@/features/dashboard/AdminDashboard';
import { FarmDashboard } from '@/features/dashboard/FarmDashboard';
import { TechnicianDashboard } from '@/features/dashboard/TechnicianDashboard';
import { VetDashboard } from '@/features/dashboard/VetDashboard';
import { useAuthStore } from '@/store/useAuthStore';

export default function DashboardScreen() {
  const role = useAuthStore((s) => s.user?.role ?? 'technician');

  switch (role) {
    case 'admin':
      return <AdminDashboard />;
    case 'farm':
      return <FarmDashboard />;
    case 'vet':
      return <VetDashboard />;
    default:
      return <TechnicianDashboard />;
  }
}
