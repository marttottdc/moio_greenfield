import { createContext, useContext, useState, useCallback, type ReactNode } from "react";

type AppBarAction = {
  onClick: () => void;
  label?: string;
} | null;

const AppBarActionContext = createContext<{
  action: AppBarAction;
  setAction: (action: AppBarAction) => void;
}>({
  action: null,
  setAction: () => {},
});

export function AppBarActionProvider({ children }: { children: ReactNode }) {
  const [action, setActionState] = useState<AppBarAction>(null);
  const setAction = useCallback((a: AppBarAction) => setActionState(a), []);
  return (
    <AppBarActionContext.Provider value={{ action, setAction }}>
      {children}
    </AppBarActionContext.Provider>
  );
}

export function useAppBarAction() {
  return useContext(AppBarActionContext);
}
