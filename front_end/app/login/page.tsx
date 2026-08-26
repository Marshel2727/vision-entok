"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Eye, EyeOff, ScanLine } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { api } from "@/lib/api";
import { Button, Card, Input } from "@/components/ui";

const schema = z.object({ username: z.string().min(3, "Username minimal 3 karakter"), password: z.string().min(8, "Password minimal 8 karakter") });
type FormData = z.infer<typeof schema>;

export default function LoginPage() {
  const router = useRouter();
  const [show, setShow] = useState(false);
  const [error, setError] = useState("");
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<FormData>({ resolver: zodResolver(schema) });
  async function submit(values: FormData) { setError(""); try { await api("/api/auth/login", { method: "POST", body: JSON.stringify(values) }); router.replace("/dashboard"); router.refresh(); } catch (err) { setError(err instanceof Error ? err.message : "Login gagal."); } }

  return <main className="grid min-h-screen lg:grid-cols-2"><section className="hidden bg-slate-950 p-12 text-white lg:flex lg:flex-col lg:justify-between"><div className="flex items-center gap-3"><div className="grid size-12 place-items-center rounded-2xl bg-emerald-500 text-slate-950"><ScanLine/></div><div><p className="text-xl font-bold">Entok Vision</p><p className="text-sm text-slate-400">AI health monitoring</p></div></div><div><p className="max-w-xl text-4xl font-bold leading-tight">Pantau kondisi mata entok dengan deteksi visual yang cepat dan terdokumentasi.</p><p className="mt-5 max-w-lg text-slate-400">Dashboard lokal untuk upload, monitoring kamera, riwayat, dan verifikasi operator.</p></div><p className="text-xs text-slate-500">Prediksi AI bukan diagnosis veteriner.</p></section><section className="flex items-center justify-center p-5"><Card className="w-full max-w-md border-0 p-7 shadow-xl sm:p-9"><div className="mb-7 lg:hidden"><div className="mb-3 grid size-12 place-items-center rounded-2xl bg-emerald-500"><ScanLine/></div><p className="text-xl font-bold">Entok Vision</p></div><h1 className="text-2xl font-bold">Selamat datang</h1><p className="mt-2 text-sm text-slate-500">Masuk menggunakan akun admin atau operator.</p><form className="mt-7 space-y-5" onSubmit={handleSubmit(submit)}><label className="block text-sm font-medium">Username<Input autoComplete="username" className="mt-2" placeholder="contoh: operator1" {...register("username")}/>{errors.username && <span className="mt-1 block text-xs text-rose-600">{errors.username.message}</span>}</label><label className="block text-sm font-medium">Password<div className="relative mt-2"><Input type={show ? "text" : "password"} autoComplete="current-password" className="pr-11" {...register("password")}/><button type="button" aria-label="Tampilkan password" className="absolute right-3 top-3 text-slate-400" onClick={() => setShow(!show)}>{show ? <EyeOff size={19}/> : <Eye size={19}/>}</button></div>{errors.password && <span className="mt-1 block text-xs text-rose-600">{errors.password.message}</span>}</label>{error && <div className="rounded-xl bg-rose-50 p-3 text-sm text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">{error}</div>}<Button className="w-full" type="submit" disabled={isSubmitting}>{isSubmitting ? "Memproses..." : "Masuk"}</Button></form></Card></section></main>;
}
