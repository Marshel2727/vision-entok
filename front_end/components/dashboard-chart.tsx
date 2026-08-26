"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export function DashboardChart({ data }: { data: Array<Record<string, string | number>> }) {
  return <div className="h-72 w-full"><ResponsiveContainer><LineChart data={data}><CartesianGrid strokeDasharray="3 3" opacity={0.25}/><XAxis dataKey="date" tick={{ fontSize: 11 }}/><YAxis allowDecimals={false} tick={{ fontSize: 11 }}/><Tooltip/><Legend/><Line type="monotone" dataKey="normal" stroke="#10b981" strokeWidth={2}/><Line type="monotone" dataKey="abnormal" stroke="#ef4444" strokeWidth={2}/><Line type="monotone" dataKey="no_detection" name="Tidak terdeteksi" stroke="#f59e0b" strokeWidth={2}/></LineChart></ResponsiveContainer></div>;
}
