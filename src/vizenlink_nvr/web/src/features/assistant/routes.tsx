import { AssistantPage } from "./AssistantPage";
import type { ShellRoute } from "@/app/routes";
export const routes: ShellRoute[] = [{ path: "/assistant", title: "AI Assistant", minRole: "viewer", element: <AssistantPage /> }];
