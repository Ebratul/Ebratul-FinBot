"use client";

import { useAuth } from "@/context/AuthContext";
import { useRouter, usePathname } from "next/navigation";
import styles from "./Navbar.module.css";

const ROLE_LABELS = {
  employee: "Employee",
  finance: "Finance",
  engineering: "Engineering",
  marketing: "Marketing",
  c_level: "C-Level Executive",
};

const ROLE_ICONS = {
  employee: "👤",
  finance: "💰",
  engineering: "⚙️",
  marketing: "📢",
  c_level: "👑",
};

export default function Navbar() {
  const { user, logoutUser } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  if (!user) return null;

  const handleLogout = () => {
    logoutUser();
    router.push("/");
  };

  const handleCollectionClick = (collection) => {
    window.dispatchEvent(new CustomEvent("finbot:collection-select", {
      detail: collection,
    }));
    router.push(`/chat?collection=${encodeURIComponent(collection)}`);
  };

  return (
    <nav className={styles.navbar}>
      <div className={styles.left}>
        <div className={styles.logo} onClick={() => router.push("/chat")}>
          <span className={styles.logoIcon}>🤖</span>
          <span className={styles.logoText}>Ebratul FinBot</span>
        </div>
        <div className={styles.navLinks}>
          <button
            className={`${styles.navLink} ${pathname === "/chat" ? styles.active : ""}`}
            onClick={() => router.push("/chat")}
          >
            💬 Chat
          </button>
          {user.is_admin && (
            <button
              className={`${styles.navLink} ${pathname === "/admin" ? styles.active : ""}`}
              onClick={() => router.push("/admin")}
            >
              🛠️ Admin
            </button>
          )}
        </div>
      </div>

      <div className={styles.right}>
        <div className={styles.userInfo}>
          <span className={styles.roleIcon}>{ROLE_ICONS[user.role] || "👤"}</span>
          <div className={styles.userMeta}>
            <span className={styles.userName}>{user.display_name}</span>
            <span className={styles.userRole}>{ROLE_LABELS[user.role] || user.role}</span>
          </div>
        </div>
        <div className={styles.collections}>
          {user.accessible_collections?.map((c) => (
            <button
              key={c}
              type="button"
              className={`${styles.collectionButton} badge badge-gold`}
              onClick={() => handleCollectionClick(c)}
              aria-label={`Ask about ${c} documents`}
            >
              {c}
            </button>
          ))}
        </div>
        <button className={`btn btn-secondary btn-sm ${styles.logoutBtn}`} onClick={handleLogout}>
          Sign Out
        </button>
      </div>
    </nav>
  );
}
