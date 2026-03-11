/**
 * PWA utilities: service worker registration, push notifications, geolocation.
 * Used by the main client app for installability, location, and notifications.
 */

/** Check if we're in a secure context (required for service worker, geolocation, notifications). */
export function isPwaCapable(): boolean {
  return typeof window !== "undefined" && window.isSecureContext;
}

/** Request notification permission. Returns current permission state. */
export async function requestNotificationPermission(): Promise<NotificationPermission> {
  if (typeof window === "undefined" || !("Notification" in window)) {
    return "denied";
  }
  if (Notification.permission === "granted") return "granted";
  if (Notification.permission === "denied") return "denied";
  return await Notification.requestPermission();
}

/** Check if notifications are supported and permitted. */
export function canShowNotifications(): boolean {
  return (
    typeof window !== "undefined" &&
    "Notification" in window &&
    "serviceWorker" in navigator &&
    Notification.permission === "granted"
  );
}

/** Show a browser notification (requires permission). */
export async function showNotification(
  title: string,
  options?: NotificationOptions
): Promise<void> {
  if (!canShowNotifications()) return;
  const reg = await navigator.serviceWorker.ready;
  if (reg.active) {
    await reg.showNotification(title, {
      icon: "/favicon.png",
      badge: "/favicon.png",
      ...options,
    });
  } else {
    new Notification(title, {
      icon: "/favicon.png",
      ...options,
    });
  }
}

/** Get current geolocation (prompts user if not yet granted). */
export function requestGeolocation(): Promise<{
  ok: boolean;
  coords?: { latitude: number; longitude: number };
  error?: string;
}> {
  if (typeof window === "undefined" || !navigator?.geolocation) {
    return Promise.resolve({ ok: false, error: "Geolocation not supported" });
  }
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        resolve({
          ok: true,
          coords: {
            latitude: pos.coords.latitude,
            longitude: pos.coords.longitude,
          },
        }),
      (err) =>
        resolve({
          ok: false,
          error: err?.message || "Permission denied or unavailable",
        }),
      { timeout: 10000, maximumAge: 60000 }
    );
  });
}
