"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ScanLine, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import type { DetectionEvent } from "@/lib/types";
import { formatConfidence, formatDate } from "@/lib/utils";
import { Badge, Card, EmptyState, PageTitle } from "@/components/ui";
import { DashboardChart } from "@/components/dashboard-chart";

type Summary = { total: number; normal: number; abnormal: number; no_detection: number; failed: number; abnormal_percentage: number; trends: Array<Record<string, string | number>>; recent_abnormal: DetectionEvent[] };

export default function DashboardPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["dashboard"], queryFn: () => api<Summary>("/api/dashboard/summary") });
  if (isLoading) return <div className="animate-pulse-soft py-20 text-center text-slate-500">Memuat dashboard...</div>;
  if (error) return <EmptyState title="Dashboard gagal dimuat" description={`${error.message}. Klik untuk mencoba kembali.`}/>;
  const summary = data!.data;
  const cards = [{ label: "Total pemeriksaan", value: summary.total, icon: ScanLine, color: "text-sky-600 bg-sky-100" }, { label: "Normal", value: summary.normal, icon: CheckCircle2, color: "text-emerald-600 bg-emerald-100" }, { label: "Abnormal", value: summary.abnormal, icon: AlertTriangle, color: "text-rose-600 bg-rose-100" }, { label: "Gagal", value: summary.failed, icon: XCircle, color: "text-amber-600 bg-amber-100" }];
  return <><PageTitle title="Dashboard" description="Ringkasan kondisi dan aktivitas deteksi terbaru."/><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{cards.map(({ label, value, icon: Icon, color }) => <Card key={label} className="flex items-center justify-between"><div><p className="text-sm text-slate-500">{label}</p><p className="mt-2 text-3xl font-bold">{value}</p></div><div className={`grid size-12 place-items-center rounded-2xl ${color}`}><Icon/></div></Card>)}</div><div className="mt-6 grid gap-6 xl:grid-cols-[1.5fr_1fr]"><Card><div className="mb-5 flex items-center justify-between"><div><h2 className="font-bold">Tren 14 hari</h2><p className="text-sm text-slate-500">Distribusi hasil pemeriksaan</p></div><Badge tone={summary.abnormal_percentage > 20 ? "red" : "green"}>{summary.abnormal_percentage}% abnormal</Badge></div>{summary.trends.length ? <DashboardChart data={summary.trends}/> : <EmptyState title="Belum ada tren" description="Data akan muncul setelah deteksi pertama."/>}</Card><Card><h2 className="font-bold">Abnormal terbaru</h2><p className="mb-5 text-sm text-slate-500">Prioritaskan pemeriksaan ulang</p><div className="space-y-3">{summary.recent_abnormal.length ? summary.recent_abnormal.map((event) => <Link key={event.id} href={`/history/${event.id}`} className="block rounded-xl border border-slate-200 p-3 transition hover:border-rose-300 dark:border-slate-800"><div className="flex items-center justify-between"><Badge tone="red">Abnormal</Badge><span className="text-xs text-slate-500">{formatConfidence(event.max_confidence)}</span></div><p className="mt-2 text-sm font-medium">{event.image?.original_filename ?? `Kamera · Event #${event.id}`}</p><p className="text-xs text-slate-500">{formatDate(event.detected_at)}</p></Link>) : <EmptyState title="Belum ada abnormal" description="Tidak ada hasil abnormal terbaru."/>}</div></Card></div></>;
}
