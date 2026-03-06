import { useEffect, useRef } from "react";
import { useLocation } from "wouter";

interface MetaJson {
  version: string;
  buildId: string;
  buildDate: string;
  timestamp: number;
}

let currentBuildId: string | null = null;
let isFirstLoad = true;

async function fetchMetaJson(): Promise<MetaJson | null> {
  try {
    const response = await fetch("/meta.json", {
      cache: "no-store",
      headers: {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
      },
    });

    if (!response.ok) {
      return null;
    }

    return await response.json();
  } catch (error) {
    return null;
  }
}

async function clearCachesAndReload() {
  if ("caches" in window) {
    try {
      const cacheNames = await caches.keys();
      await Promise.all(cacheNames.map((name) => caches.delete(name)));
    } catch (error) {
      // Silently fail to clear caches
    }
  }

  window.location.reload();
}

export function CacheBuster({ children }: { children: React.ReactNode }) {
  const [location] = useLocation();
  const hasCheckedRef = useRef(false);

  useEffect(() => {
    async function checkVersion() {
      const meta = await fetchMetaJson();
      if (!meta?.buildId) {
        return;
      }

      if (isFirstLoad) {
        currentBuildId = meta.buildId;
        isFirstLoad = false;
        return;
      }

      if (currentBuildId && currentBuildId !== meta.buildId) {
        await clearCachesAndReload();
      }
    }

    if (!hasCheckedRef.current || location) {
      hasCheckedRef.current = true;
      checkVersion();
    }
  }, [location]);

  return <>{children}</>;
}

export async function getBuildInfo(): Promise<MetaJson | null> {
  return fetchMetaJson();
}
