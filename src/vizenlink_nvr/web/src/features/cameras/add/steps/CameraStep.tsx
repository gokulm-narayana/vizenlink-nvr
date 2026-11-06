import React from "react";
import { Link } from "react-router";
import type { UseFormReturn } from "react-hook-form";
import { Field, FieldLabel, FieldDescription, FieldError } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PasswordField } from "@/components/PasswordField";
import type { AddCameraFormValues } from "../schema";
import { ADD_CAMERA_COPY } from "../copy";

export interface CameraStepProps {
  form: UseFormReturn<AddCameraFormValues>;
  disabled?: boolean;
}

export const CameraStep: React.FC<CameraStepProps> = ({ form, disabled = false }) => {
  const {
    register,
    formState: { errors },
    watch,
  } = form;

  const serialValue = watch("serial");
  const serialError = errors.serial;
  const is409Conflict =
    serialError?.message?.includes("already exists") ?? false;

  return (
    <div className="flex flex-col gap-4">
      {/* Serial Number */}
      <Field className="flex flex-col gap-1">
        <FieldLabel htmlFor="camera-serial" className="text-xs font-semibold">
          {ADD_CAMERA_COPY.SERIAL_LABEL}
        </FieldLabel>
        <Input
          id="camera-serial"
          placeholder="e.g. CAM-01"
          autoComplete="off"
          disabled={disabled}
          className="text-sm font-normal"
          {...register("serial")}
        />
        {serialError ? (
          <div className="flex flex-col gap-1">
            <FieldError>{serialError.message}</FieldError>
            {is409Conflict && serialValue && (
              <Link
                to={`/cameras/${encodeURIComponent(serialValue.trim())}`}
                className="text-xs font-semibold text-primary-text hover:underline inline-flex items-center gap-1"
              >
                {ADD_CAMERA_COPY.OPEN_EXISTING_CAMERA(serialValue.trim())}
              </Link>
            )}
          </div>
        ) : (
          <FieldDescription className="text-xs text-muted-foreground">
            {ADD_CAMERA_COPY.SERIAL_HELPER}
          </FieldDescription>
        )}
      </Field>

      {/* Host / IP address */}
      <Field className="flex flex-col gap-1">
        <FieldLabel htmlFor="camera-host" className="text-xs font-semibold">
          {ADD_CAMERA_COPY.HOST_LABEL}
        </FieldLabel>
        <Input
          id="camera-host"
          placeholder="192.168.1.100"
          autoComplete="off"
          disabled={disabled}
          className="text-sm font-normal"
          {...register("host")}
        />
        {errors.host && <FieldError>{errors.host.message}</FieldError>}
      </Field>

      {/* HTTPS Port */}
      <Field className="flex flex-col gap-1">
        <FieldLabel htmlFor="camera-port" className="text-xs font-semibold">
          {ADD_CAMERA_COPY.PORT_LABEL}
        </FieldLabel>
        <Input
          id="camera-port"
          type="number"
          min={1}
          max={65535}
          disabled={disabled}
          className="text-sm font-normal"
          {...register("https_port", { valueAsNumber: true })}
        />
        {errors.https_port && (
          <FieldError>{errors.https_port.message}</FieldError>
        )}
      </Field>

      {/* Username */}
      <Field className="flex flex-col gap-1">
        <FieldLabel htmlFor="camera-username" className="text-xs font-semibold">
          {ADD_CAMERA_COPY.USERNAME_LABEL}
        </FieldLabel>
        <Input
          id="camera-username"
          autoComplete="off"
          disabled={disabled}
          className="text-sm font-normal"
          {...register("username")}
        />
        {errors.username && (
          <FieldError>{errors.username.message}</FieldError>
        )}
      </Field>

      {/* Password */}
      <Field className="flex flex-col gap-1">
        <FieldLabel htmlFor="camera-password" className="text-xs font-semibold">
          {ADD_CAMERA_COPY.PASSWORD_LABEL}
        </FieldLabel>
        <PasswordField
          id="camera-password"
          autoComplete="off"
          disabled={disabled}
          className="text-sm font-normal"
          {...register("password")}
        />
        {errors.password ? (
          <FieldError>{errors.password.message}</FieldError>
        ) : (
          <FieldDescription className="text-xs text-muted-foreground">
            {ADD_CAMERA_COPY.PASSWORD_HELPER}
          </FieldDescription>
        )}
      </Field>
    </div>
  );
};
