import "./globals.css";
import { AuthProvider } from "@/context/AuthContext";

export const metadata = {
  title: "FinBot — FinSolve Technologies AI Assistant",
  description:
    "Internal AI-powered Q&A assistant with role-based access control for FinSolve Technologies employees.",
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
