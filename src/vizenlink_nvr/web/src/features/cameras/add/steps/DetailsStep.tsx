import React from "react";
import type { UseFormReturn } from "react-hook-form";
import { Field, FieldLabel, FieldDescription, FieldError } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import type { AddCameraFormValues } from "../schema";
import { ADD_CAMERA_COPY } from "../copy";

export interface DetailsStepProps {
  form: UseFormReturn<AddCameraFormValues>;
  disabled?: boolean;
}

export const DetailsStep: React.FC<DetailsStepProps> = ({ form, disabled = false }) => {
  const {
    register,
    formState: { errors },
  } = form;

  return (
    <div className="flex flex-col gap-4">
      {/* Camera Name */}
      <Field className="flex flex-col gap-1">
        <FieldLabel htmlFor="camera-name" className="text-xs font-semibold">
          {ADD_CAMERA_COPY.NAME_LABEL}
        </FieldLabel>
        <Input
          id="camera-name"
          placeholder="Optional (defaults to serial)"
          autoComplete="off"
          disabled={disabled}
          className="text-sm font-normal"
          {...register("name")}
        />
        {errors.name ? (
          <FieldError>{errors.name.message}</FieldError>
        ) : (
          <FieldDescription className="text-xs text-muted-foreground">
            {ADD_CAMERA_COPY.NAME_HELPER}
          </FieldDescription>
        )}
      </Field>

      {/* Location */}
      <Field className="flex flex-col gap-1">
        <FieldLabel htmlFor="camera-location" className="text-xs font-semibold">
          {ADD_CAMERA_COPY.LOCATION_LABEL}
        </FieldLabel>
        <Input
          id="camera-location"
          placeholder="e.g. Front Door, Warehouse"
          autoComplete="off"
          disabled={disabled}
          className="text-sm font-normal"
          {...register("location")}
        />
        {errors.location ? (
          <FieldError>{errors.location.message}</FieldError>
        ) : (
          <FieldDescription className="text-xs text-muted-foreground">
            {ADD_CAMERA_COPY.LOCATION_HELPER}
          </FieldDescription>
        )}
      </Field>

      {/* Group */}
      <Field className="flex flex-col gap-1">
        <FieldLabel htmlFor="camera-group" className="text-xs font-semibold">
          {ADD_CAMERA_COPY.GROUP_LABEL}
        </FieldLabel>
        <Input
          id="camera-group"
          placeholder="e.g. default, exterior"
          autoComplete="off"
          disabled={disabled}
          className="text-sm font-normal"
          {...register("group_tag")}
        />
        {errors.group_tag ? (
          <FieldError>{errors.group_tag.message}</FieldError>
        ) : (
          <FieldDescription className="text-xs text-muted-foreground">
            {ADD_CAMERA_COPY.GROUP_HELPER}
          </FieldDescription>
        )}
      </Field>
    </div>
  );
};
