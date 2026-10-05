import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ViLabs HR Assistant",
  description: "Το κεντρικό HR chat για ερωτήσεις και αιτήματα εργαζομένων."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="el"><body>{children}</body></html>;
}
