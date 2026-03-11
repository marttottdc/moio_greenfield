import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import i18n from "@/i18n";
import { apiV1 } from "@/lib/api";
import { fetchJson, apiRequest } from "@/lib/queryClient";
import { useAuth } from "@/contexts/AuthContext";

const LOCALIZATION_PATH = apiV1("/settings/localization/");

interface LocalizationData {
  language: string;
  timezone: string;
  currency: string;
  system_defaults?: {
    language: string;
    timezone: string;
    currency: string;
  };
}

interface LocaleContextType {
  locale: string;
  timezone: string;
  currency: string;
  systemDefaults?: LocalizationData["system_defaults"];
  isLoading: boolean;
  setLocale: (language: string) => Promise<void>;
  setTimezone: (timezone: string) => Promise<void>;
  setCurrency: (currency: string) => Promise<void>;
}

const LocaleContext = createContext<LocaleContextType | undefined>(undefined);

export function LocaleProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const queryClient = useQueryClient();
  const [initialized, setInitialized] = useState(false);

  const {
    data,
    isLoading,
    isSuccess,
  } = useQuery<LocalizationData>({
    queryKey: ["localization"],
    queryFn: () => fetchJson<LocalizationData>(LOCALIZATION_PATH),
    retry: false,
    staleTime: 5 * 60 * 1000,
    enabled: isAuthenticated,
  });

  const mutation = useMutation({
    mutationFn: async (payload: Partial<LocalizationData>) => {
      const res = await apiRequest("PATCH", LOCALIZATION_PATH, { data: payload });
      return res.json();
    },
    onSuccess: (result) => {
      queryClient.setQueryData(["localization"], (prev: LocalizationData | undefined) =>
        prev ? { ...prev, ...result } : result
      );
    },
  });

  useEffect(() => {
    if (isSuccess && data?.language && !initialized) {
      const lang = data.language === "pt" ? "pt" : data.language === "es" ? "es" : "en";
      if (i18n.language !== lang) {
        i18n.changeLanguage(lang);
      }
      localStorage.setItem("moio-locale", lang);
      setInitialized(true);
    }
  }, [isSuccess, data?.language, initialized]);

  const setLocale = useCallback(
    async (language: string) => {
      const lang = language === "pt" ? "pt" : language === "es" ? "es" : "en";
      // Optimistic update: change UI immediately so user sees the switch
      localStorage.setItem("moio-locale", lang);
      await i18n.changeLanguage(lang);
      await mutation.mutateAsync({ language });
    },
    [mutation]
  );

  const setTimezone = useCallback(
    async (timezone: string) => {
      await mutation.mutateAsync({ timezone });
    },
    [mutation]
  );

  const setCurrency = useCallback(
    async (currency: string) => {
      await mutation.mutateAsync({ currency });
    },
    [mutation]
  );

  const value: LocaleContextType = {
    locale: data?.language || "en",
    timezone: data?.timezone || "UTC",
    currency: data?.currency || "USD",
    systemDefaults: data?.system_defaults,
    isLoading,
    setLocale,
    setTimezone,
    setCurrency,
  };

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  const context = useContext(LocaleContext);
  if (context === undefined) {
    return {
      locale: "en",
      timezone: "UTC",
      currency: "USD",
      isLoading: false,
      setLocale: async () => {},
      setTimezone: async () => {},
      setCurrency: async () => {},
    } as LocaleContextType;
  }
  return context;
}
