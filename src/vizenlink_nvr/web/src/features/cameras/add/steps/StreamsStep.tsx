import React, { useState } from "react";
import type { UseFormReturn } from "react-hook-form";
import { ChevronDown } from "lucide-react";
import { Field, FieldLabel, FieldDescription, FieldError } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Button } from "@/components/ui/button";
import { useUiStore } from "@/stores/ui";
import { ReviewList } from "../ReviewList";
import type { AddCameraFormValues } from "../schema";
import { ADD_CAMERA_COPY } from "../copy";
import { cn } from "cn";

export interface StreamsStepProps {
  form: UseFormReturn<AddCameraFormValues>;
  disabled?: boolean;
}

export const StreamsStep: React.FC<StreamsStepProps> = ({ form, disabled = false }) => {
  const {
    register,
    watch,
    setValue,
    formState: { errors },
  } = form;

  const viewMode = useUiStore((s) => s.viewMode);
  const isAdvanced = viewMode === "advanced";
  const [detailsOpen, setDetailsOpen] = useState(false);

  const hasSubStream = watch("has_sub_stream");
  const mainScheme = watch("main_scheme");
  const subScheme = watch("sub_scheme");

  return (
    <div className="flex flex-col gap-6">
      {/* Main Stream Section */}
      <div className="flex flex-col gap-4 rounded-lg border border-border p-4 bg-card">
        <span className="text-sm font-semibold text-foreground">
          {ADD_CAMERA_COPY.MAIN_STREAM_TITLE}
        </span>

        {/* Scheme */}
        <Field className="flex flex-col gap-2">
          <FieldLabel className="text-xs font-semibold">
            {ADD_CAMERA_COPY.SCHEME_LABEL}
          </FieldLabel>
          <RadioGroup
            value={mainScheme}
            onValueChange={(val) =>
              setValue("main_scheme", val as "rtsp" | "rtsps", { shouldDirty: true })
            }
            disabled={disabled}
            className="flex items-center gap-4"
          >
            <div className="flex items-center gap-2">
              <RadioGroupItem value="rtsp" id="main-scheme-rtsp" />
              <Label
                htmlFor="main-scheme-rtsp"
                className="text-xs font-normal text-foreground cursor-pointer"
              >
                rtsp
              </Label>
            </div>
            <div className="flex items-center gap-2">
              <RadioGroupItem value="rtsps" id="main-scheme-rtsps" />
              <Label
                htmlFor="main-scheme-rtsps"
                className="text-xs font-normal text-foreground cursor-pointer"
              >
                rtsps
              </Label>
            </div>
          </RadioGroup>
        </Field>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Port */}
          <Field className="flex flex-col gap-1">
            <FieldLabel htmlFor="main-port" className="text-xs font-semibold">
              {ADD_CAMERA_COPY.STREAM_PORT_LABEL}
            </FieldLabel>
            <Input
              id="main-port"
              type="number"
              min={1}
              max={65535}
              disabled={disabled}
              className="text-sm font-normal"
              {...register("main_port", { valueAsNumber: true })}
            />
            {errors.main_port && (
              <FieldError>{errors.main_port.message}</FieldError>
            )}
          </Field>

          {/* Path */}
          <Field className="flex flex-col gap-1">
            <FieldLabel htmlFor="main-path" className="text-xs font-semibold">
              {ADD_CAMERA_COPY.PATH_LABEL}
            </FieldLabel>
            <Input
              id="main-path"
              placeholder="/stream1"
              autoComplete="off"
              disabled={disabled}
              className="text-sm font-normal"
              {...register("main_path")}
            />
            {errors.main_path && (
              <FieldError>{errors.main_path.message}</FieldError>
            )}
          </Field>
        </div>
      </div>

      {/* Sub Stream Section */}
      <div className="flex flex-col gap-4 rounded-lg border border-border p-4 bg-card">
        <div className="flex items-center justify-between gap-4">
          <div className="flex flex-col gap-1">
            <Label
              htmlFor="add-sub-stream"
              className="text-sm font-semibold text-foreground cursor-pointer"
            >
              {ADD_CAMERA_COPY.SUB_STREAM_TOGGLE}
            </Label>
            <span className="text-xs text-muted-foreground">
              Optional lower-resolution stream for responsive multi-camera live grid tiles.
            </span>
          </div>
          <Switch
            id="add-sub-stream"
            checked={hasSubStream}
            onCheckedChange={(checked) =>
              setValue("has_sub_stream", checked, { shouldDirty: true, shouldValidate: true })
            }
            disabled={disabled}
          />
        </div>

        {hasSubStream && (
          <div className="flex flex-col gap-4 pt-4 border-t border-border">
            {/* Sub Scheme */}
            <Field className="flex flex-col gap-2">
              <FieldLabel className="text-xs font-semibold">
                {ADD_CAMERA_COPY.SCHEME_LABEL}
              </FieldLabel>
              <RadioGroup
                value={subScheme}
                onValueChange={(val) =>
                  setValue("sub_scheme", val as "rtsp" | "rtsps", { shouldDirty: true })
                }
                disabled={disabled}
                className="flex items-center gap-4"
              >
                <div className="flex items-center gap-2">
                  <RadioGroupItem value="rtsp" id="sub-scheme-rtsp" />
                  <Label
                    htmlFor="sub-scheme-rtsp"
                    className="text-xs font-normal text-foreground cursor-pointer"
                  >
                    rtsp
                  </Label>
                </div>
                <div className="flex items-center gap-2">
                  <RadioGroupItem value="rtsps" id="sub-scheme-rtsps" />
                  <Label
                    htmlFor="sub-scheme-rtsps"
                    className="text-xs font-normal text-foreground cursor-pointer"
                  >
                    rtsps
                  </Label>
                </div>
              </RadioGroup>
            </Field>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Sub Port */}
              <Field className="flex flex-col gap-1">
                <FieldLabel htmlFor="sub-port" className="text-xs font-semibold">
                  {ADD_CAMERA_COPY.STREAM_PORT_LABEL}
                </FieldLabel>
                <Input
                  id="sub-port"
                  type="number"
                  min={1}
                  max={65535}
                  disabled={disabled}
                  className="text-sm font-normal"
                  {...register("sub_port", { valueAsNumber: true })}
                />
                {errors.sub_port && (
                  <FieldError>{errors.sub_port.message}</FieldError>
                )}
              </Field>

              {/* Sub Path */}
              <Field className="flex flex-col gap-1">
                <FieldLabel htmlFor="sub-path" className="text-xs font-semibold">
                  {ADD_CAMERA_COPY.PATH_LABEL}
                </FieldLabel>
                <Input
                  id="sub-path"
                  placeholder="/stream2"
                  autoComplete="off"
                  disabled={disabled}
                  className="text-sm font-normal"
                  {...register("sub_path")}
                />
                {errors.sub_path ? (
                  <FieldError>{errors.sub_path.message}</FieldError>
                ) : (
                  <FieldDescription className="text-xs text-muted-foreground">
                    {ADD_CAMERA_COPY.SUB_PATH_HELPER}
                  </FieldDescription>
                )}
              </Field>
            </div>
          </div>
        )}
      </div>

      {/* Advanced Stream Details (collapsible in advanced view) */}
      {isAdvanced && (
        <Collapsible
          open={detailsOpen}
          onOpenChange={setDetailsOpen}
          className="flex flex-col gap-2 rounded-lg border border-border p-4 bg-muted/10"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-foreground uppercase tracking-wider">
              {ADD_CAMERA_COPY.STREAM_DETAILS_TITLE}
            </span>
            <CollapsibleTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="gap-1 text-xs"
              >
                <span>{detailsOpen ? "Hide" : "Show"} details</span>
                <ChevronDown
                  className={cn(
                    "h-3.5 w-3.5 transition-transform duration-200",
                    detailsOpen && "rotate-180"
                  )}
                />
              </Button>
            </CollapsibleTrigger>
          </div>

          <CollapsibleContent className="flex flex-col gap-4 pt-2">
            <div className="flex flex-col gap-2">
              <span className="text-xs font-semibold text-foreground">
                Main stream tokens & resolution
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <Field className="flex flex-col gap-1">
                  <FieldLabel className="text-xs font-normal">
                    {ADD_CAMERA_COPY.CODEC_LABEL}
                  </FieldLabel>
                  <Input
                    disabled={disabled}
                    className="text-xs font-normal"
                    {...register("main_codec")}
                  />
                </Field>
                <Field className="flex flex-col gap-1">
                  <FieldLabel className="text-xs font-normal">
                    {ADD_CAMERA_COPY.WIDTH_LABEL}
                  </FieldLabel>
                  <Input
                    type="number"
                    disabled={disabled}
                    className="text-xs font-normal"
                    {...register("main_width", { valueAsNumber: true })}
                  />
                </Field>
                <Field className="flex flex-col gap-1">
                  <FieldLabel className="text-xs font-normal">
                    {ADD_CAMERA_COPY.HEIGHT_LABEL}
                  </FieldLabel>
                  <Input
                    type="number"
                    disabled={disabled}
                    className="text-xs font-normal"
                    {...register("main_height", { valueAsNumber: true })}
                  />
                </Field>
              </div>
            </div>

            {hasSubStream && (
              <div className="flex flex-col gap-2 pt-2 border-t border-border/50">
                <span className="text-xs font-semibold text-foreground">
                  Sub stream tokens & resolution
                </span>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  <Field className="flex flex-col gap-1">
                    <FieldLabel className="text-xs font-normal">
                      {ADD_CAMERA_COPY.CODEC_LABEL}
                    </FieldLabel>
                    <Input
                      disabled={disabled}
                      className="text-xs font-normal"
                      {...register("sub_codec")}
                    />
                  </Field>
                  <Field className="flex flex-col gap-1">
                    <FieldLabel className="text-xs font-normal">
                      {ADD_CAMERA_COPY.WIDTH_LABEL}
                    </FieldLabel>
                    <Input
                      type="number"
                      disabled={disabled}
                      className="text-xs font-normal"
                      {...register("sub_width", { valueAsNumber: true })}
                    />
                  </Field>
                  <Field className="flex flex-col gap-1">
                    <FieldLabel className="text-xs font-normal">
                      {ADD_CAMERA_COPY.HEIGHT_LABEL}
                    </FieldLabel>
                    <Input
                      type="number"
                      disabled={disabled}
                      className="text-xs font-normal"
                      {...register("sub_height", { valueAsNumber: true })}
                    />
                  </Field>
                </div>
              </div>
            )}
          </CollapsibleContent>
        </Collapsible>
      )}

      {/* Review List */}
      <ReviewList values={watch()} />
    </div>
  );
};
