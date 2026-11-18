import type { Metadata } from "next";
import "./globals.css";
import Header from "@/components/Header";
import { AlertsProvider } from "@/lib/alerts";
import { AuthProvider } from "@/lib/auth";
import { WatchlistProvider } from "@/lib/watchlist";

export const metadata: Metadata = {
  title: "Stock Insights",
  description: "Why your stocks moved, and which ones deserve a look today.",
};

// Runs before first paint so the saved theme never flashes.
const themeScript = `try{var p=localStorage.getItem('theme')||'system';var d=p==='dark'||(p==='system'&&matchMedia('(prefers-color-scheme: dark)').matches);var r=document.documentElement;r.dataset.theme=d?'dark':'light';r.dataset.cb=localStorage.getItem('cb')==='1'?'1':'0'}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: themeScript }} /></head>
      <body>
        <AuthProvider>
          <WatchlistProvider>
            <AlertsProvider>
              <Header />
              <main><div className="wrap">{children}</div></main>
            </AlertsProvider>
          </WatchlistProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
