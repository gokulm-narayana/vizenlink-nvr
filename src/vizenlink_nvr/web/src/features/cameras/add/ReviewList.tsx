import React from "react";
import type { AddCameraFormValues } from "./schema";
import { ADD_CAMERA_COPY } from "./copy";

export interface ReviewListProps {
  values: AddCameraFormValues;
}

export const ReviewList: React.FC<ReviewListProps> = ({ values }) => {
  const serial = values.serial?.trim() || "";
  const host = values.host?.trim() || "";
  const port = values.https_port || 443;
  const name = values.name?.trim() || serial;
  const location = values.location?.trim() || "Default";
  const group = values.group_tag?.trim() || "default";

  const mainStreamSummary = `${values.main_scheme}://${host}:${values.main_port || 554}${values.main_path || "/stream1"}`;
  const subStreamSummary = values.has_sub_stream
    ? `${values.sub_scheme}://${host}:${values.sub_port || 554}${values.sub_path}`
    : "None";

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-muted/20 p-4">
      <span className="text-xs font-semibold text-foreground uppercase tracking-wider">
        {ADD_CAMERA_COPY.REVIEW_TITLE}
      </span>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
        <div>
          <span className="text-muted-foreground">{ADD_CAMERA_COPY.REVIEW_SERIAL}: </span>
          <span className="font-mono text-foreground">{serial}</span>
        </div>
        <div>
          <span className="text-muted-foreground">{ADD_CAMERA_COPY.REVIEW_ADDRESS}: </span>
          <span className="font-mono text-foreground">
            {host}:{port}
          </span>
        </div>
        <div>
          <span className="text-muted-foreground">{ADD_CAMERA_COPY.REVIEW_NAME}: </span>
          <span className="text-foreground">{name}</span>
        </div>
        <div>
          <span className="text-muted-foreground">{ADD_CAMERA_COPY.REVIEW_LOCATION}: </span>
          <span className="text-foreground">{location}</span>
        </div>
        <div>
          <span className="text-muted-foreground">{ADD_CAMERA_COPY.REVIEW_GROUP}: </span>
          <span className="text-foreground">{group}</span>
        </div>
        <div>
          <span className="text-muted-foreground">{ADD_CAMERA_COPY.REVIEW_PASSWORD}: </span>
          <span className="font-mono text-foreground tracking-widest">••••••••</span>
        </div>
      </div>

      <div className="flex flex-col gap-1 text-xs pt-1 border-t border-border/50">
        <span className="text-muted-foreground">{ADD_CAMERA_COPY.REVIEW_STREAMS}:</span>
        <div className="flex flex-col gap-0.5 pl-2 font-mono text-foreground text-xs">
          <span>Main: {mainStreamSummary}</span>
          {values.has_sub_stream && <span>Sub: {subStreamSummary}</span>}
        </div>
      </div>
    </div>
  );
};
