import { AppSidebar } from '../app-sidebar';
import { SidebarProvider } from "@/components/ui/sidebar";

export default function AppSidebarExample() {
  const style = {
    "--sidebar-width": "15rem",
  };

  return (
    <SidebarProvider style={style as React.CSSProperties}>
      <AppSidebar />
    </SidebarProvider>
  );
}
