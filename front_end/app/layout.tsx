import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = { title: "Entok Vision", description: "Dashboard deteksi kondisi mata entok" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="id" suppressHydrationWarning><body className="min-h-screen antialiased"><Providers>{children}</Providers></body></html>;
}
