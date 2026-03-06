import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { UserDashboardPreferences, WidgetConfig, KPIType, FavoriteItem } from "@shared/schema";
import { DEFAULT_DASHBOARD_PREFERENCES } from "@shared/schema";

const LOCAL_PREFERENCES_URL = "/api/v1/settings/preferences/";
const PREFERENCES_QUERY_KEY = ["local-dashboard-preferences"];

async function fetchLocalPreferences(): Promise<UserDashboardPreferences> {
  try {
    const response = await fetch(LOCAL_PREFERENCES_URL);
    if (!response.ok) {
      console.warn("[Preferences] Local endpoint returned error, using defaults");
      return DEFAULT_DASHBOARD_PREFERENCES;
    }
    const data = await response.json();
    if (data.layout_version !== undefined) {
      return data as UserDashboardPreferences;
    }
    console.warn("[Preferences] Response schema mismatch, using defaults");
    return DEFAULT_DASHBOARD_PREFERENCES;
  } catch (error) {
    console.warn("[Preferences] Failed to fetch, using defaults:", error);
    return DEFAULT_DASHBOARD_PREFERENCES;
  }
}

async function patchLocalPreferences(
  updates: Partial<UserDashboardPreferences>
): Promise<UserDashboardPreferences> {
  const response = await fetch(LOCAL_PREFERENCES_URL, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  if (!response.ok) {
    throw new Error("Failed to update preferences");
  }
  return response.json() as Promise<UserDashboardPreferences>;
}

type PreferencesUpdater = (current: UserDashboardPreferences) => Partial<UserDashboardPreferences>;

type MutationQueueItem = {
  updater: PreferencesUpdater;
  resolve: (value: UserDashboardPreferences) => void;
  reject: (error: Error) => void;
};

let mutationQueue: MutationQueueItem[] = [];
let isProcessing = false;

async function processQueue(queryClient: ReturnType<typeof useQueryClient>) {
  if (isProcessing || mutationQueue.length === 0) {
    return;
  }

  isProcessing = true;

  while (mutationQueue.length > 0) {
    const item = mutationQueue.shift()!;
    
    try {
      const current = await queryClient.ensureQueryData({
        queryKey: PREFERENCES_QUERY_KEY,
        queryFn: fetchLocalPreferences,
      });
      
      const updates = item.updater(current);
      
      const result = await patchLocalPreferences(updates);
      queryClient.setQueryData(PREFERENCES_QUERY_KEY, result);
      item.resolve(result);
    } catch (error) {
      item.reject(error as Error);
    }
  }

  isProcessing = false;
}

export function usePreferences() {
  const queryClient = useQueryClient();

  const query = useQuery<UserDashboardPreferences>({
    queryKey: PREFERENCES_QUERY_KEY,
    queryFn: fetchLocalPreferences,
    staleTime: 1000 * 60 * 5,
  });

  const mutation = useMutation({
    mutationFn: async (updater: PreferencesUpdater) => {
      return new Promise<UserDashboardPreferences>((resolve, reject) => {
        mutationQueue.push({ updater, resolve, reject });
        processQueue(queryClient);
      });
    },
  });

  const updatePreferences = (updater: PreferencesUpdater) => {
    return mutation.mutateAsync(updater);
  };

  return {
    preferences: query.data ?? DEFAULT_DASHBOARD_PREFERENCES,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    updatePreferences,
    isUpdating: mutation.isPending,
  };
}

export function useWidgets() {
  const { preferences, updatePreferences, isUpdating } = usePreferences();
  
  const widgets = preferences.widgets;
  const enabledWidgets = widgets
    .filter((w) => w.enabled)
    .sort((a, b) => a.order - b.order);

  const updateWidgets = async (newWidgets: WidgetConfig[]) => {
    await updatePreferences(() => ({ widgets: newWidgets }));
  };

  return {
    widgets,
    enabledWidgets,
    updateWidgets,
    isUpdating,
  };
}

export function useKPIs() {
  const { preferences, updatePreferences, isUpdating } = usePreferences();
  
  const kpis = preferences.kpis;
  
  const updateKPIs = async (visible_kpis: KPIType[]) => {
    await updatePreferences((current) => ({ 
      kpis: { ...current.kpis, visible_kpis } 
    }));
  };

  const toggleKPIRibbon = async (enabled: boolean) => {
    await updatePreferences((current) => ({ 
      kpis: { ...current.kpis, enabled } 
    }));
  };

  return {
    kpis,
    visibleKPIs: kpis.visible_kpis,
    updateKPIs,
    toggleKPIRibbon,
    isUpdating,
  };
}

export function useAssistantPreferences() {
  const { preferences, updatePreferences, isUpdating } = usePreferences();
  
  const assistant = preferences.assistant;

  const toggleSidebar = async () => {
    await updatePreferences((current) => ({ 
      assistant: { ...current.assistant, sidebar_collapsed: !current.assistant.sidebar_collapsed } 
    }));
  };

  const setSidebarCollapsed = async (collapsed: boolean) => {
    await updatePreferences((current) => ({ 
      assistant: { ...current.assistant, sidebar_collapsed: collapsed } 
    }));
  };

  return {
    assistant,
    isSidebarCollapsed: assistant.sidebar_collapsed,
    toggleSidebar,
    setSidebarCollapsed,
    isUpdating,
  };
}

export function useFavorites() {
  const { preferences, updatePreferences, isUpdating } = usePreferences();
  
  const favorites = preferences.favorites;

  const addFavorite = async (item: FavoriteItem) => {
    await updatePreferences((current) => {
      if (current.favorites.find((f) => f.id === item.id)) {
        return {};
      }
      return { favorites: [...current.favorites, item] };
    });
  };

  const removeFavorite = async (id: string) => {
    await updatePreferences((current) => ({ 
      favorites: current.favorites.filter((f) => f.id !== id) 
    }));
  };

  const isFavorite = (id: string) => favorites.some((f) => f.id === id);

  return {
    favorites,
    addFavorite,
    removeFavorite,
    isFavorite,
    isUpdating,
  };
}
