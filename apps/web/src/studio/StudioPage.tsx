import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { studioHost } from "./api";
import { createStudio } from "./engine.js";
import studioCss from "./studio.css?inline";

type StudioHandle = {
  start: () => Promise<void>;
  destroy: () => void;
  flush: () => Promise<unknown>;
};

/**
 * RIHRP Offline Research Studio の WebUI。
 *
 * 正本（ルート直下の RIHRP_Offline_Research_Studio.html）のマークアップ・文言・
 * ルールベース処理をそのまま移植し、永続化だけをサーバー API に置き換える。
 * アプリ本体のグローバル CSS と干渉しないよう Shadow DOM に隔離する。
 */
export function StudioPage() {
  const hostRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { logout } = useAuth();

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const controller = new AbortController();
    const shadow = host.shadowRoot ?? host.attachShadow({ mode: "open" });
    shadow.innerHTML = "";
    const style = document.createElement("style");
    style.textContent = studioCss;
    shadow.appendChild(style);
    const root = document.createElement("div");
    root.className = "studio-root";
    shadow.appendChild(root);

    let studio: StudioHandle | null = null;
    studio = createStudio(root, {
      ...studioHost,
      onAdmin: () => navigate("/audit"),
      onLogout: () => {
        void (async () => {
          try {
            await studio?.flush();
          } finally {
            await logout().finally(() => navigate("/login", { replace: true }));
          }
        })();
      },
      onConflict: () => window.location.reload(),
    }, { signal: controller.signal }) as StudioHandle;

    let disposed = false;
    void studio.start().catch((error: unknown) => {
      if (disposed) return;
      const message = error instanceof Error ? error.message : "研究データを読み込めませんでした。";
      root.innerHTML = "";
      const wrap = document.createElement("div");
      wrap.style.padding = "40px";
      const card = document.createElement("div");
      card.className = "card";
      const title = document.createElement("h2");
      title.textContent = "読み込みに失敗しました";
      const detail = document.createElement("p");
      detail.className = "muted";
      detail.textContent = message;
      const retry = document.createElement("button");
      retry.className = "btn pri";
      retry.textContent = "再読み込み";
      retry.addEventListener("click", () => window.location.reload());
      card.append(title, detail, retry);
      wrap.appendChild(card);
      root.appendChild(wrap);
    });

    return () => {
      disposed = true;
      controller.abort();
      studio?.destroy();
    };
  }, [navigate, logout]);

  return <div ref={hostRef} style={{ minHeight: "100vh" }} />;
}
