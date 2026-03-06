import { Link } from "wouter";
import { GlassPanel } from "@/components/radiant/glass-panel";
import { Subheading } from "@/components/radiant/text";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Star, X, Megaphone, Users, Briefcase, FileText, Workflow } from "lucide-react";
import { useFavorites } from "@/hooks/use-preferences";
import type { FavoriteItem } from "@shared/schema";

const TYPE_ICONS: Record<FavoriteItem["type"], typeof Star> = {
  page: FileText,
  campaign: Megaphone,
  contact: Users,
  deal: Briefcase,
  workflow: Workflow,
};

export function FavoritesWidget() {
  const { favorites, removeFavorite, isUpdating } = useFavorites();

  return (
    <GlassPanel className="p-6 h-full" data-testid="widget-favorites">
      <div className="flex items-center justify-between mb-4">
        <Subheading className="flex items-center gap-2">
          <Star className="h-4 w-4 text-yellow-500" />
          Favorites
        </Subheading>
      </div>

      {favorites.length === 0 ? (
        <EmptyState
          title="No favorites"
          description="Star items to add them here for quick access."
        />
      ) : (
        <div className="space-y-2">
          {favorites.map((item) => {
            const Icon = TYPE_ICONS[item.type] || Star;
            return (
              <div
                key={item.id}
                className="flex items-center justify-between p-2 rounded-lg hover-elevate group"
                data-testid={`favorite-item-${item.id}`}
              >
                <Link
                  href={item.path || "#"}
                  className="flex items-center gap-2 flex-1"
                >
                  <Icon className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm">{item.name}</span>
                </Link>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={() => removeFavorite(item.id)}
                  disabled={isUpdating}
                  data-testid={`button-remove-favorite-${item.id}`}
                >
                  <X className="h-3 w-3" />
                </Button>
              </div>
            );
          })}
        </div>
      )}

      {favorites.length === 0 && (
        <p className="text-xs text-muted-foreground text-center mt-4 border-t pt-4">
          <span className="opacity-60">[Demo Data]</span> Sample favorites will appear after you star items.
        </p>
      )}
    </GlassPanel>
  );
}
