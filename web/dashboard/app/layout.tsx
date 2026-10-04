import type { Metadata } from "next";
import { LocaleProvider } from "@/lib/locale";
import "./globals.css";

export const metadata: Metadata = { title: "Smart Pump · Care workspace", description: "Prototype feeding-pump dashboard. Fictional demo data." };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en" suppressHydrationWarning><head><script dangerouslySetInnerHTML={{ __html: "try{document.documentElement.dataset.theme=localStorage.getItem('sp-theme')==='night'?'night':'day'}catch{}" }} /></head><body><LocaleProvider>{children}</LocaleProvider></body></html>;
}
