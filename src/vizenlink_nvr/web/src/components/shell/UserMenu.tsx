import React, { useState } from "react";
import { Link } from "react-router";
import { User, Sun, Moon, Monitor, LogOut, KeyRound } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useCurrentUser } from "@/lib/queries";
import { useUiStore, type Theme, type ViewMode } from "@/stores/ui";
import { useSignOut } from "@/features/auth/api";
import { isRegistered } from "@/app/routes";
import { ChangePasswordDialog } from "@/features/profile/ChangePasswordDialog";

export const UserMenu: React.FC = () => {
  const [isChangePasswordOpen, setIsChangePasswordOpen] = useState(false);
  const user = useCurrentUser();
  const theme = useUiStore((s) => s.theme);
  const setTheme = useUiStore((s) => s.setTheme);
  const viewMode = useUiStore((s) => s.viewMode);
  const setViewMode = useUiStore((s) => s.setViewMode);
  const signOut = useSignOut();

  const username = user?.username || "User";
  const role = user?.role || "viewer";
  const initial = username.charAt(0).toUpperCase() || "U";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="rounded-full"
          aria-label={`Account menu for ${username}`}
        >
          <Avatar className="h-8 w-8">
            <AvatarFallback className="bg-muted text-foreground text-xs font-semibold">
              {initial}
            </AvatarFallback>
          </Avatar>
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="font-normal">
          <div className="flex items-center justify-between gap-2">
            <span className="truncate text-sm font-semibold">{username}</span>
            <Badge variant="secondary" className="text-xs font-semibold">
              {role}
            </Badge>
          </div>
        </DropdownMenuLabel>

        {isRegistered("/profile") && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild>
              <Link to="/profile" className="flex items-center gap-2">
                <User className="h-4 w-4" />
                <span>Profile</span>
              </Link>
            </DropdownMenuItem>
          </>
        )}

        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => setIsChangePasswordOpen(true)}>
          <KeyRound className="h-4 w-4 mr-2" />
          <span>Change password</span>
        </DropdownMenuItem>

        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
          Theme
        </DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={theme}
          onValueChange={(val) => setTheme(val as Theme)}
        >
          <DropdownMenuRadioItem value="light">
            <Sun className="h-4 w-4 mr-2" />
            <span>Light</span>
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark">
            <Moon className="h-4 w-4 mr-2" />
            <span>Dark</span>
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="system">
            <Monitor className="h-4 w-4 mr-2" />
            <span>System</span>
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>

        <div className="md:hidden">
          <DropdownMenuSeparator />
          <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
            View
          </DropdownMenuLabel>
          <DropdownMenuRadioGroup
            value={viewMode}
            onValueChange={(val) => setViewMode(val as ViewMode)}
          >
            <DropdownMenuRadioItem value="simple">
              <span>Simple</span>
            </DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="advanced">
              <span>Advanced</span>
            </DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
        </div>

        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => void signOut()}>
          <LogOut className="h-4 w-4 mr-2" />
          <span>Sign out</span>
        </DropdownMenuItem>
      </DropdownMenuContent>

      <ChangePasswordDialog
        open={isChangePasswordOpen}
        onOpenChange={setIsChangePasswordOpen}
      />
    </DropdownMenu>
  );
};

export default UserMenu;
