import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { apiRequest } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";

const LOCATION_SAVE_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes
const LOCATION_PATH = apiV1("/settings/location/");

/** Obtiene ubicación vía geolocalización + Nominatim; puede fallar por extensiones (location-spoofing). */
async function fetchUserLocation(): Promise<string | null> {
  if (typeof window === "undefined" || !navigator?.geolocation) return null;
  return new Promise((resolve) => {
    try {
      navigator.geolocation.getCurrentPosition(
        async (pos) => {
          const { latitude, longitude } = pos.coords;
          try {
            const res = await fetch(
              `https://nominatim.openstreetmap.org/reverse?format=json&lat=${latitude}&lon=${longitude}`,
              { headers: { "Accept-Language": "es", "User-Agent": "MoioCRM/1.0" } }
            );
            const data = await res.json();
            resolve(data?.display_name ?? `${latitude}, ${longitude}`);
          } catch {
            resolve(`${latitude}, ${longitude}`);
          }
        },
        () => resolve(null),
        { timeout: 10000, maximumAge: 60000 }
      );
    } catch {
      resolve(null);
    }
  });
}

type UserLocationContextType = {
  lastLocation: string | null;
  isSaving: boolean;
};

const UserLocationContext = createContext<UserLocationContextType | undefined>(undefined);

export function UserLocationProvider({ children }: { children: ReactNode }) {
  const { user, isAuthenticated } = useAuth();
  const [lastLocation, setLastLocation] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const fromUser = (user as { preferences?: { last_location?: string } } | null)?.preferences?.last_location ?? null;
  const effective = lastLocation ?? fromUser ?? null;

  const saveLocation = useCallback(async (address: string) => {
    if (!address?.trim()) return;
    setIsSaving(true);
    try {
      await apiRequest("PATCH", LOCATION_PATH, { data: { address: address.trim() } });
      setLastLocation(address.trim());
    } catch {
      // Fallo silencioso
    } finally {
      setIsSaving(false);
    }
  }, []);

  useEffect(() => {
    if (!isAuthenticated || !user) return;

    const tick = async () => {
      const addr = await fetchUserLocation();
      if (addr) await saveLocation(addr);
    };

    tick();
    const id = setInterval(tick, LOCATION_SAVE_INTERVAL_MS);
    return () => clearInterval(id);
  }, [isAuthenticated, user?.id, saveLocation]);

  const value: UserLocationContextType = {
    lastLocation: effective,
    isSaving,
  };

  return (
    <UserLocationContext.Provider value={value}>
      {children}
    </UserLocationContext.Provider>
  );
}

export function useUserLocation(): UserLocationContextType {
  const ctx = useContext(UserLocationContext);
  if (ctx === undefined) {
    return { lastLocation: null, isSaving: false };
  }
  return ctx;
}
