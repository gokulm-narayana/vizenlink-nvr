import React from "react";
import { UsersPage } from "./UsersPage";
import type { ShellRoute } from "@/app/routes";

export const routes: ShellRoute[] = [
  {
    path: "/users",
    title: "Users",
    minRole: "owner",
    element: <UsersPage />,
  },
];
