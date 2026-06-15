"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AdminPanel } from "@/components/admin/AdminPanel";
import { useApp } from "@/contexts/AppContext";

export default function AdminPage() {
  const { isAdmin } = useApp();
  const router = useRouter();

  useEffect(() => {
    if (!isAdmin) router.replace("/soporte");
  }, [isAdmin, router]);

  if (!isAdmin) return null;

  return <AdminPanel />;
}
