import "./globals.css";
import { AuthProvider } from "@/context/AuthContext";

export const metadata = {
  title: "Ebratul FinBot — Ebratul Technologies AI Assistant",
  description:
    "Internal AI-powered Q&A assistant with role-based access control for Ebratul Technologies employees.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
