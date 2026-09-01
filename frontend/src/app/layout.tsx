import type { Metadata } from "next";
import { Providers } from "@/components/layout/Providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "Soporte Batán",
  description:
    "Soporte Batán — asistido por Eko, tu asistente virtual. Internet Ecolan, móvil IMOWI y WhatsApp.",
  icons: {
    icon: "/eko-avatar.png",
    apple: "/eko-avatar.png",
  },
};

const themeBootScript = `(function(){try{var t=localStorage.getItem('ops-hub-theme');if(t!=='light'&&t!=='dark')t='dark';document.documentElement.setAttribute('data-theme',t);document.documentElement.style.colorScheme=t;}catch(e){document.documentElement.setAttribute('data-theme','dark');}})();`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es" className="h-full antialiased" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootScript }} />
      </head>
      <body className="min-h-full flex flex-col bg-background text-foreground transition-colors duration-200">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
