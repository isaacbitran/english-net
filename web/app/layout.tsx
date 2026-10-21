import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import "./globals.css";

/* Newsreader (Production Type) and Inter (Rasmus Andersson), both SIL OFL 1.1, bundled so the demo works offline. */
const serif = localFont({
  src: [
    { path: "./fonts/Newsreader-latin.woff2", style: "normal", weight: "200 800" },
    { path: "./fonts/Newsreader-italic-latin.woff2", style: "italic", weight: "200 800" },
  ],
  variable: "--font-serif",
  display: "swap",
});
const sans = localFont({ src: "./fonts/Inter-latin.woff2", weight: "100 900", variable: "--font-sans", display: "swap" });

export const metadata: Metadata = {
  title: "English Net",
  description:
    "A prompt-injection detector whose neurons are English yes/no questions. It ties one good question on unseen data, and one added sentence fixed a blind spot.",
};

export const viewport: Viewport = { themeColor: "#faf9f5" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${serif.variable} ${sans.variable}`}>
      <body>{children}</body>
    </html>
  );
}
