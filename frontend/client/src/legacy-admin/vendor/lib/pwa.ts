// @ts-nocheck
type BeforeInstallPromptEventLike = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform?: string }>;
};

const INSTALL_EVENT = "moio:pwa-install-available";
let deferredPrompt: BeforeInstallPromptEventLike | null = null;
let listenersBound = false;

function emitInstallEvent(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(INSTALL_EVENT, { detail: { available: deferredPrompt !== null } }));
}

function bindInstallListeners(): void {
  if (listenersBound || typeof window === "undefined") return;
  listenersBound = true;
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferredPrompt = event as BeforeInstallPromptEventLike;
    emitInstallEvent();
  });
  window.addEventListener("appinstalled", () => {
    deferredPrompt = null;
    emitInstallEvent();
  });
}

export function installPromptEventName(): string {
  return INSTALL_EVENT;
}

export async function registerPwa(): Promise<ServiceWorkerRegistration | null> {
  bindInstallListeners();
  if (typeof window === "undefined" || !("serviceWorker" in navigator) || !window.isSecureContext) {
    return null;
  }
  try {
    const registration = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
    return registration;
  } catch {
    return null;
  }
}

export function isInstallPromptAvailable(): boolean {
  return deferredPrompt !== null;
}

export async function promptInstall(): Promise<boolean> {
  const promptEvent = deferredPrompt;
  if (!promptEvent) return false;
  await promptEvent.prompt();
  const choice = await promptEvent.userChoice;
  deferredPrompt = null;
  emitInstallEvent();
  return choice.outcome === "accepted";
}

export async function requestNotificationPermission(): Promise<NotificationPermission | "unsupported"> {
  if (typeof window === "undefined" || typeof Notification === "undefined") {
    return "unsupported";
  }
  let permission = Notification.permission;
  if (permission === "default") {
    permission = await Notification.requestPermission();
  }
  if (permission !== "granted") {
    return permission;
  }
  const registration = await registerPwa();
  try {
    if (registration) {
      await registration.showNotification("Moio is ready", {
        body: "Notifications are enabled on this device.",
        icon: "/pwa-icon.svg",
        badge: "/pwa-icon.svg",
        tag: "moio-ready",
      });
    }
  } catch {
    // Ignore display failures; permission itself succeeded.
  }
  return permission;
}

function base64UrlToUint8Array(value: string): Uint8Array {
  const normalized = String(value || "").trim();
  if (!normalized) return new Uint8Array();
  const padding = "=".repeat((4 - (normalized.length % 4 || 4)) % 4);
  const base64 = `${normalized}${padding}`.replace(/-/g, "+").replace(/_/g, "/");
  const decoded = atob(base64);
  const output = new Uint8Array(decoded.length);
  for (let index = 0; index < decoded.length; index += 1) {
    output[index] = decoded.charCodeAt(index);
  }
  return output;
}

function bufferToBase64(input: ArrayBuffer | null): string {
  if (!input) return "";
  const bytes = new Uint8Array(input);
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

export type PushProfile = {
  serviceWorkerReady: boolean;
  pushManagerSupported: boolean;
  userAgent: string;
  platform: string;
  language: string;
  enabledAt: string;
  subscription: {
    endpoint: string;
    expirationTime: number | null;
    keys: Record<string, string>;
  } | null;
};

export async function requestPushNotifications(vapidPublicKey = ""): Promise<{
  permission: NotificationPermission | "unsupported";
  profile: PushProfile | null;
}> {
  const permission = await requestNotificationPermission();
  const registration = await registerPwa();
  let subscriptionPayload: PushProfile["subscription"] = null;
  if (permission === "granted" && registration && "pushManager" in registration) {
    try {
      let subscription = await registration.pushManager.getSubscription();
      const pushKey = String(vapidPublicKey || "").trim();
      if (!subscription && pushKey) {
        subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: base64UrlToUint8Array(pushKey),
        });
      }
      if (subscription) {
        subscriptionPayload = {
          endpoint: subscription.endpoint,
          expirationTime: subscription.expirationTime ?? null,
          keys: {
            p256dh: bufferToBase64(subscription.getKey("p256dh")),
            auth: bufferToBase64(subscription.getKey("auth")),
          },
        };
      }
    } catch {
      subscriptionPayload = null;
    }
  }
  if (typeof window === "undefined") {
    return { permission, profile: null };
  }
  return {
    permission,
    profile: {
      serviceWorkerReady: Boolean(registration),
      pushManagerSupported: Boolean(registration && "pushManager" in registration),
      userAgent: typeof navigator !== "undefined" ? String(navigator.userAgent || "") : "",
      platform: typeof navigator !== "undefined" ? String(navigator.platform || "") : "",
      language: typeof navigator !== "undefined" ? String(navigator.language || "") : "",
      enabledAt: new Date().toISOString(),
      subscription: subscriptionPayload,
    },
  };
}

export async function showBrowserNotification(
  title: string,
  body: string,
  tag = "moio-event",
  url = "/",
  options?: {
    icon?: string;
    badge?: string;
    requireInteraction?: boolean;
    renotify?: boolean;
    silent?: boolean;
  },
): Promise<boolean> {
  if (typeof window === "undefined" || typeof Notification === "undefined") {
    return false;
  }
  if (Notification.permission !== "granted") {
    return false;
  }
  try {
    const registration = await registerPwa();
    if (registration) {
      await registration.showNotification(title, {
        body,
        icon: options?.icon || "/pwa-icon.svg",
        badge: options?.badge || "/pwa-icon.svg",
        tag,
        requireInteraction: Boolean(options?.requireInteraction),
        renotify: Boolean(options?.renotify),
        silent: Boolean(options?.silent),
        data: { url },
      });
      return true;
    }
  } catch {
    // Fall back to the page-level notification object below.
  }
  try {
    // eslint-disable-next-line no-new
    new Notification(title, {
      body,
      icon: options?.icon || "/pwa-icon.svg",
      badge: options?.badge || "/pwa-icon.svg",
      tag,
      requireInteraction: Boolean(options?.requireInteraction),
      renotify: Boolean(options?.renotify),
      silent: Boolean(options?.silent),
      data: { url },
    });
    return true;
  } catch {
    return false;
  }
}

export type GeoResult =
  | { ok: true; latitude: number; longitude: number; accuracy: number }
  | { ok: false; error: string };

export async function requestGeolocation(): Promise<GeoResult> {
  if (typeof window === "undefined" || !("geolocation" in navigator)) {
    return { ok: false, error: "unsupported" };
  }
  return await new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (position) =>
        resolve({
          ok: true,
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy,
        }),
      (error) => resolve({ ok: false, error: error.message || "permission denied" }),
      {
        enableHighAccuracy: false,
        timeout: 10000,
        maximumAge: 300000,
      },
    );
  });
}
