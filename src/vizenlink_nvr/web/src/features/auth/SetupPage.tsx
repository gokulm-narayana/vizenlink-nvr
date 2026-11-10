import React, { useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { BrandLogo } from "@/components/BrandLogo";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PasswordField } from "@/components/PasswordField";
import { NativeSelect } from "@/components/ui/native-select";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { ApiError } from "@/lib/api";
import { useSetup } from "./api";
import { AUTH_COPY } from "./copy";

const setupSchema = z
  .object({
    owner_username: z.string().min(1, "Owner username is required"),
    owner_password: z.string().min(8, AUTH_COPY.PASSWORD_TOO_SHORT),
    confirm_password: z.string().min(1, "Confirm password is required"),
    timezone: z.string().min(1, "Time zone is required"),
    storage_path: z.string().min(1, "Storage path is required"),
    allow_system_disk: z.boolean(),
  })
  .refine((data) => data.owner_password === data.confirm_password, {
    message: AUTH_COPY.PASSWORD_MISMATCH,
    path: ["confirm_password"],
  });

type SetupFormValues = z.infer<typeof setupSchema>;

function resolveTimezones(): { list: string[]; defaultTz: string } {
  let defaultTz = "UTC";
  try {
    const resolved = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (resolved) {
      defaultTz = resolved;
    }
  } catch {
    // fallback to UTC
  }

  let list: string[] = [];
  try {
    const intlAny = Intl as unknown as { supportedValuesOf?: (key: string) => string[] };
    if (typeof intlAny.supportedValuesOf === "function") {
      list = intlAny.supportedValuesOf("timeZone");
    }
  } catch {
    // fallback
  }

  if (list.length === 0) {
    list = [defaultTz, "UTC"].filter((v, i, a) => a.indexOf(v) === i);
  } else if (!list.includes(defaultTz)) {
    list = [defaultTz, ...list].sort();
  }

  return { list, defaultTz };
}

export const SetupPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const setupMutation = useSetup();

  const [formError, setFormError] = useState<string | null>(null);
  const [serverDetail, setServerDetail] = useState<string | null>(null);

  const { list: timezones, defaultTz } = useMemo(() => resolveTimezones(), []);

  const {
    register,
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<SetupFormValues>({
    resolver: zodResolver(setupSchema),
    defaultValues: {
      owner_username: "",
      owner_password: "",
      confirm_password: "",
      timezone: defaultTz,
      storage_path: "/var/lib/vizenlink-nvr/recordings",
      allow_system_disk: false,
    },
  });

  const onSubmit = async (values: SetupFormValues) => {
    setFormError(null);
    setServerDetail(null);
    try {
      await setupMutation.mutateAsync({
        owner_username: values.owner_username,
        owner_password: values.owner_password,
        timezone: values.timezone,
        storage_path: values.storage_path,
        allow_system_disk: Boolean(values.allow_system_disk),
      });
      await queryClient.invalidateQueries({ queryKey: ["authStatus"] });
      void navigate("/", { replace: true });
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setFormError(AUTH_COPY.SETUP_FAILURE);
        setServerDetail(err.detail);
      } else {
        setFormError(AUTH_COPY.SETUP_FAILURE);
      }
    }
  };

  return (
    <div className="flex min-h-dvh flex-col items-center pt-16 px-4">
      <BrandLogo variant="full" />
      <div className="mt-4 w-full max-w-lg">
        <Card className="p-6">
          <CardHeader className="p-0 mb-4">
            <h1 className="text-xl font-semibold leading-[1.2]">
              {AUTH_COPY.TITLE_SETUP}
            </h1>
          </CardHeader>
          <CardContent className="p-0">
            {formError && (
              <Alert variant="destructive" role="alert" className="mb-4">
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription className="text-sm font-normal">
                  {formError}
                  {serverDetail && (
                    <span className="block mt-1 text-xs font-normal text-muted-foreground">
                      {serverDetail}
                    </span>
                  )}
                </AlertDescription>
                <div className="mt-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={isSubmitting || setupMutation.isPending}
                    onClick={() => void handleSubmit(onSubmit)()}
                  >
                    {AUTH_COPY.RETRY_SETUP}
                  </Button>
                </div>
              </Alert>
            )}

            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
              <Field data-invalid={Boolean(errors.owner_username)}>
                <FieldLabel htmlFor="owner_username">Owner username</FieldLabel>
                <Input
                  id="owner_username"
                  autoComplete="username"
                  aria-invalid={Boolean(errors.owner_username)}
                  {...register("owner_username")}
                />
                {errors.owner_username && (
                  <FieldError className="text-xs font-normal">
                    {errors.owner_username.message}
                  </FieldError>
                )}
              </Field>

              <Field data-invalid={Boolean(errors.owner_password)}>
                <FieldLabel htmlFor="password">Password</FieldLabel>
                <PasswordField
                  id="password"
                  autoComplete="new-password"
                  aria-invalid={Boolean(errors.owner_password)}
                  {...register("owner_password")}
                />
                {errors.owner_password ? (
                  <FieldError className="text-xs font-normal">
                    {errors.owner_password.message}
                  </FieldError>
                ) : (
                  <FieldDescription className="text-xs font-normal">
                    {AUTH_COPY.PASSWORD_HELPER}
                  </FieldDescription>
                )}
              </Field>

              <Field data-invalid={Boolean(errors.confirm_password)}>
                <FieldLabel htmlFor="confirm_password">Confirm password</FieldLabel>
                <PasswordField
                  id="confirm_password"
                  autoComplete="new-password"
                  aria-invalid={Boolean(errors.confirm_password)}
                  {...register("confirm_password")}
                />
                {errors.confirm_password && (
                  <FieldError className="text-xs font-normal">
                    {errors.confirm_password.message}
                  </FieldError>
                )}
              </Field>

              <Field data-invalid={Boolean(errors.timezone)}>
                <FieldLabel htmlFor="timezone">{AUTH_COPY.SITE_TIMEZONE_LABEL}</FieldLabel>
                <NativeSelect
                  id="timezone"
                  className="w-full"
                  aria-invalid={Boolean(errors.timezone)}
                  {...register("timezone")}
                >
                  {timezones.map((tz) => (
                    <option key={tz} value={tz}>
                      {tz}
                    </option>
                  ))}
                </NativeSelect>
                {errors.timezone && (
                  <FieldError className="text-xs font-normal">
                    {errors.timezone.message}
                  </FieldError>
                )}
              </Field>

              <Field data-invalid={Boolean(errors.storage_path)}>
                <FieldLabel htmlFor="storage_path">
                  {AUTH_COPY.RECORDING_STORAGE_LABEL}
                </FieldLabel>
                <Input
                  id="storage_path"
                  aria-invalid={Boolean(errors.storage_path)}
                  {...register("storage_path")}
                />
                {errors.storage_path && (
                  <FieldError className="text-xs font-normal">
                    {errors.storage_path.message}
                  </FieldError>
                )}
              </Field>

              <Field orientation="horizontal" className="items-start gap-2">
                <Controller
                  control={control}
                  name="allow_system_disk"
                  render={({ field }) => (
                    <Checkbox
                      id="allow_system_disk"
                      aria-label={AUTH_COPY.ALLOW_SYSTEM_DISK_LABEL}
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  )}
                />
                <div className="flex flex-col gap-1">
                  <FieldLabel
                    htmlFor="allow_system_disk"
                    className="text-sm font-semibold cursor-pointer"
                  >
                    {AUTH_COPY.ALLOW_SYSTEM_DISK_LABEL}
                  </FieldLabel>
                  <FieldDescription className="text-xs font-normal">
                    {AUTH_COPY.ALLOW_SYSTEM_DISK_HELPER}
                  </FieldDescription>
                </div>
              </Field>

              <Button
                type="submit"
                className="w-full mt-4"
                disabled={isSubmitting || setupMutation.isPending}
              >
                {isSubmitting || setupMutation.isPending ? (
                  <>
                    <Spinner className="mr-2 h-4 w-4" />
                    {AUTH_COPY.CREATE_OWNER_ACCOUNT}
                  </>
                ) : (
                  AUTH_COPY.CREATE_OWNER_ACCOUNT
                )}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default SetupPage;