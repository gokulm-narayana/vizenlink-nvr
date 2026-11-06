import React, { useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useQueryClient } from "@tanstack/react-query";
import { AlertCircle, AlertTriangle } from "lucide-react";
import { BrandLogo } from "@/components/BrandLogo";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PasswordField } from "@/components/PasswordField";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { safeNext } from "@/lib/safe-next";
import { ApiError } from "@/lib/api";
import { useLogin } from "./api";
import { AUTH_COPY } from "./copy";

const loginSchema = z.object({
  username: z.string().min(1, "Username is required"),
  password: z.string().min(1, "Password is required"),
});

type LoginFormValues = z.infer<typeof loginSchema>;

export const LoginPage: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const loginMutation = useLogin();

  const [formError, setFormError] = useState<string | null>(null);
  const [signOutFailed, setSignOutFailed] = useState<boolean>(
    Boolean(location.state?.signOutFailed)
  );
  const [retryingSignOut, setRetryingSignOut] = useState(false);

  const isSessionEnded = Boolean(location.state?.sessionEnded);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      username: "",
      password: "",
    },
  });

  const onSubmit = async (values: LoginFormValues) => {
    setFormError(null);
    try {
      await loginMutation.mutateAsync(values);
      await queryClient.invalidateQueries({ queryKey: ["authStatus"] });
      const nextParam = searchParams.get("next");
      const target = safeNext(nextParam) ?? "/";
      void navigate(target, { replace: true });
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setFormError(AUTH_COPY.LOGIN_ERROR);
        } else if (err.status === 429) {
          setFormError(AUTH_COPY.LOCKOUT_ERROR);
        } else {
          setFormError(err.detail || AUTH_COPY.LOGIN_ERROR);
        }
      } else {
        setFormError(AUTH_COPY.LOGIN_ERROR);
      }
    }
  };

  const handleRetrySignOut = async () => {
    setRetryingSignOut(true);
    try {
      const res = await fetch("/api/v1/auth/logout", {
        method: "POST",
        credentials: "same-origin",
      });
      if (res.ok) {
        setSignOutFailed(false);
      }
    } catch {
      // remain in failed state
    } finally {
      setRetryingSignOut(false);
    }
  };

  return (
    <div className="flex min-h-dvh flex-col items-center pt-16 px-4">
      <BrandLogo variant="full" />
      <div className="mt-4 w-full max-w-sm">
        {isSessionEnded && (
          <Alert role="status" className="mb-4">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription className="text-sm font-normal">
              {AUTH_COPY.SESSION_ENDED}
            </AlertDescription>
          </Alert>
        )}

        {signOutFailed && (
          <Alert variant="destructive" role="alert" className="mb-4">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription className="text-sm font-normal">
              {AUTH_COPY.SIGN_OUT_FAILURE}
            </AlertDescription>
            <div className="mt-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={retryingSignOut}
                onClick={() => void handleRetrySignOut()}
              >
                {retryingSignOut ? (
                  <>
                    <Spinner className="mr-2 h-4 w-4" />
                    {AUTH_COPY.RETRY_SIGN_OUT}
                  </>
                ) : (
                  AUTH_COPY.RETRY_SIGN_OUT
                )}
              </Button>
            </div>
          </Alert>
        )}

        <Card className="p-6">
          <CardHeader className="p-0 mb-4">
            <h1 className="text-xl font-semibold leading-[1.2]">
              {AUTH_COPY.TITLE_SIGN_IN}
            </h1>
          </CardHeader>
          <CardContent className="p-0">
            {formError && (
              <Alert variant="destructive" role="alert" className="mb-4">
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription className="text-sm font-normal">
                  {formError}
                </AlertDescription>
              </Alert>
            )}

            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
              <Field data-invalid={Boolean(errors.username)}>
                <FieldLabel htmlFor="username">Username</FieldLabel>
                <Input
                  id="username"
                  autoComplete="username"
                  aria-invalid={Boolean(errors.username)}
                  {...register("username")}
                />
                {errors.username && (
                  <FieldError className="text-xs font-normal">
                    {errors.username.message}
                  </FieldError>
                )}
              </Field>

              <Field data-invalid={Boolean(errors.password)}>
                <FieldLabel htmlFor="password">Password</FieldLabel>
                <PasswordField
                  id="password"
                  autoComplete="current-password"
                  aria-invalid={Boolean(errors.password)}
                  {...register("password")}
                />
                {errors.password && (
                  <FieldError className="text-xs font-normal">
                    {errors.password.message}
                  </FieldError>
                )}
              </Field>

              <Button
                type="submit"
                className="w-full mt-4"
                disabled={isSubmitting || loginMutation.isPending}
              >
                {isSubmitting || loginMutation.isPending ? (
                  <>
                    <Spinner className="mr-2 h-4 w-4" />
                    {AUTH_COPY.SIGN_IN}
                  </>
                ) : (
                  AUTH_COPY.SIGN_IN
                )}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default LoginPage;
