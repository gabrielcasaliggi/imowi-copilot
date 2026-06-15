import type { Metadata } from "next";
import { Providers } from "@/components/layout/Providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "imowi Operations Hub",
  description: "Consola operativa multitenant para soporte, NOC y gestión OSS/BSS",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-[var(--background)] text-slate-200">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
