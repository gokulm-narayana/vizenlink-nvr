import { SearchPage } from "./SearchPage";
import type { ShellRoute } from "@/app/routes";
export const routes: ShellRoute[] = [{ path: "/search", title: "Search", minRole: "viewer", element: <SearchPage /> }];
