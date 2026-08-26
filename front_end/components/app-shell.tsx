"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useTheme } from "next-themes";
import { BarChart3, Camera, History, LogOut, Menu, Moon, ScanLine, Settings, Sun, Users, X } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";
import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";

const navigation = [
  { href: "/dashboard", label: "Dashboard", icon: BarChart3 },
  { href: "/detect", label: "Deteksi Gambar", icon: ScanLine },
  { href: "/history", label: "Riwayat", icon: History },
  { href: "/monitoring", label: "Monitoring", icon: Camera },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const { data } = useQuery({ queryKey: ["me"], queryFn: () => api<User>("/api/auth/me") });
  const user = data?.data;
  const items = user?.role === "admin" ? [...navigation, { href: "/admin/users", label: "Pengguna", icon: Users }, { href: "/admin/camera", label: "Konfigurasi", icon: Settings }] : navigation;

  async function logout() { await api("/api/auth/logout", { method: "POST" }); router.replace("/login"); router.refresh(); }

  const sidebar = <div className="flex h-full flex-col bg-slate-950 text-slate-100">
    <div className="flex h-20 items-center gap-3 border-b border-slate-800 px-6"><div className="grid size-11 place-items-center rounded-2xl bg-emerald-500 text-slate-950"><ScanLine size={24}/></div><div><p className="font-bold">Entok Vision</p><p className="text-xs text-slate-400">Health monitoring</p></div></div>
    <nav className="flex-1 space-y-1 p-4">{items.map((item) => { const active = pathname === item.href || pathname.startsWith(`${item.href}/`); return <Link key={item.href} href={item.href} onClick={() => setOpen(false)} className={cn("flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition", active ? "bg-emerald-500 text-slate-950" : "text-slate-300 hover:bg-slate-900 hover:text-white")}><item.icon size={19}/>{item.label}</Link>; })}</nav>
    <div className="border-t border-slate-800 p-4"><p className="truncate text-sm font-semibold">{user?.full_name ?? "Memuat..."}</p><p className="text-xs capitalize text-slate-400">{user?.role ?? ""}</p><Button variant="ghost" className="mt-3 w-full justify-start text-slate-300 hover:bg-slate-900" onClick={logout}><LogOut size={17}/>Keluar</Button></div>
  </div>;

  return <div className="min-h-screen lg:grid lg:grid-cols-[260px_1fr]">
    <aside className="hidden h-screen lg:sticky lg:top-0 lg:block">{sidebar}</aside>
    {open && <div className="fixed inset-0 z-50 lg:hidden"><button aria-label="Tutup menu" className="absolute inset-0 bg-slate-950/60" onClick={() => setOpen(false)}/><aside className="relative h-full w-72 shadow-2xl">{sidebar}<button className="absolute right-3 top-3 p-2" onClick={() => setOpen(false)}><X/></button></aside></div>}
    <div className="min-w-0"><header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-slate-200/80 bg-white/90 px-4 backdrop-blur dark:border-slate-800 dark:bg-slate-950/90 lg:px-8"><Button variant="ghost" size="sm" className="lg:hidden" onClick={() => setOpen(true)}><Menu/></Button><div className="ml-auto flex items-center gap-2"><Button variant="ghost" size="sm" aria-label="Ganti tema" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? <Sun size={18}/> : <Moon size={18}/>}</Button><div className="hidden text-right sm:block"><p className="text-sm font-semibold">{user?.full_name}</p><p className="text-xs text-slate-500">@{user?.username}</p></div></div></header><main className="mx-auto w-full max-w-7xl p-4 sm:p-6 lg:p-8">{children}</main></div>
  </div>;
}
