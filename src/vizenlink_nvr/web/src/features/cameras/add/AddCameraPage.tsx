import React, { useState, useRef } from "react";
import { useNavigate, useBlocker } from "react-router";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { InlineError } from "@/components/InlineError";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Stepper } from "./Stepper";
import { CameraStep } from "./steps/CameraStep";
import { DetailsStep } from "./steps/DetailsStep";
import { StreamsStep } from "./steps/StreamsStep";
import { addCameraSchema, toCreateRequest, type AddCameraFormValues } from "./schema";
import { useCreateCamera } from "./api";
import { ADD_CAMERA_COPY } from "./copy";
import { ApiError } from "@/lib/api";

export const AddCameraPage: React.FC = () => {
  const navigate = useNavigate();
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [showDiscardDialog, setShowDiscardDialog] = useState<boolean>(false);
  const isSubmittingSuccessRef = useRef<boolean>(false);

  const form = useForm<AddCameraFormValues>({
    resolver: zodResolver(addCameraSchema),
    defaultValues: {
      serial: "",
      host: "",
      https_port: 443,
      username: "admin",
      password: "",
      name: "",
      location: "",
      group_tag: "",
      main_scheme: "rtsp",
      main_port: 554,
      main_path: "/stream1",
      main_codec: "H264",
      main_width: 1920,
      main_height: 1080,
      main_transport: "tcp",
      main_profile_token: "Profile_1",
      main_venc_token: "VideoEncoder_1",
      has_sub_stream: false,
      sub_scheme: "rtsp",
      sub_port: 554,
      sub_path: "",
      sub_codec: "H264",
      sub_width: 1920,
      sub_height: 1080,
      sub_transport: "tcp",
      sub_profile_token: "Profile_2",
      sub_venc_token: "VideoEncoder_2",
    },
    mode: "onBlur",
  });

  const createMutation = useCreateCamera();

  // Leave protection: check if user entered any input
  const isDirty = form.formState.isDirty;

  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      isDirty &&
      !isSubmittingSuccessRef.current &&
      currentLocation.pathname !== nextLocation.pathname
  );

  const handleDiscardClick = () => {
    if (isDirty) {
      setShowDiscardDialog(true);
    } else {
      navigate("/cameras");
    }
  };

  const handleConfirmDiscard = () => {
    setShowDiscardDialog(false);
    if (blocker.state === "blocked") {
      blocker.proceed();
    } else {
      navigate("/cameras");
    }
  };

  const handleKeepEditing = () => {
    setShowDiscardDialog(false);
    if (blocker.state === "blocked") {
      blocker.reset();
    }
  };

  const handleContinueToDetails = async () => {
    setSubmitError(null);
    const valid = await form.trigger(
      ["serial", "host", "https_port", "username", "password"],
      { shouldFocus: true }
    );
    if (!valid) return;
    setStep(2);
  };

  const handleContinueToStreams = async () => {
    setSubmitError(null);
    const valid = await form.trigger(["name", "location", "group_tag"]);
    if (!valid) {
      return;
    }
    setStep(3);
  };

  const onSubmit = async (values: AddCameraFormValues) => {
    setSubmitError(null);
    try {
      const payload = toCreateRequest(values);
      const createdCamera = await createMutation.mutateAsync(payload);
      isSubmittingSuccessRef.current = true;
      toast.success(ADD_CAMERA_COPY.SUCCESS_TOAST(payload.name));
      navigate(`/cameras/${encodeURIComponent(createdCamera.serial)}`);
    } catch (err: unknown) {
      isSubmittingSuccessRef.current = false;
      if (err instanceof ApiError && err.status === 409) {
        setStep(1);
        form.setError("serial", {
          type: "manual",
          message: ADD_CAMERA_COPY.SERIAL_EXISTS(values.serial),
        });
        form.setFocus("serial");
      } else if (err instanceof ApiError && err.status === 503) {
        setSubmitError(ADD_CAMERA_COPY.VAULT_UNAVAILABLE_ERROR);
      } else {
        setSubmitError(ADD_CAMERA_COPY.GENERIC_ADD_ERROR);
      }
    }
  };

  const isPending = createMutation.isPending;

  return (
    <div className="flex flex-col items-center justify-start p-6 min-h-full">
      {/* Header */}
      <div className="w-full max-w-xl flex flex-col gap-1 pb-6">
        <h1 className="text-xl font-semibold text-foreground tracking-tight">
          {ADD_CAMERA_COPY.TITLE}
        </h1>
        <p className="text-xs text-muted-foreground leading-relaxed">
          {ADD_CAMERA_COPY.PAGE_NOTE_PRE}
          <code className="px-1 py-0.5 rounded bg-muted font-mono text-foreground text-xs">
            {ADD_CAMERA_COPY.PAGE_NOTE_CMD}
          </code>
          {ADD_CAMERA_COPY.PAGE_NOTE_POST}
        </p>
      </div>

      {/* Wizard Card (560px max width) */}
      <Card className="w-full max-w-xl border border-border shadow-sm">
        <CardContent className="flex flex-col gap-6 p-6">
          <Stepper currentStep={step} />

          <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-6">
            {step === 1 && <CameraStep form={form} disabled={isPending} />}
            {step === 2 && <DetailsStep form={form} disabled={isPending} />}
            {step === 3 && <StreamsStep form={form} disabled={isPending} />}

            {/* Inline Error Alert */}
            {submitError && (
              <InlineError
                message={submitError}
                actionLabel={ADD_CAMERA_COPY.RETRY_ADD}
                onAction={() => form.handleSubmit(onSubmit)()}
                pending={isPending}
              />
            )}

            {/* Action Buttons */}
            <div className="flex flex-col-reverse sm:flex-row items-center justify-between gap-4 pt-4 border-t border-border">
              <Button
                type="button"
                variant="ghost"
                onClick={handleDiscardClick}
                disabled={isPending}
                className="self-start sm:self-auto text-xs"
              >
                {ADD_CAMERA_COPY.DISCARD_BUTTON}
              </Button>

              <div className="flex items-center gap-2 self-end sm:self-auto">
                {step === 1 && (
                  <Button
                    type="button"
                    variant="default"
                    onClick={handleContinueToDetails}
                    disabled={isPending}
                    className="text-xs"
                  >
                    {ADD_CAMERA_COPY.CONTINUE_TO_DETAILS}
                  </Button>
                )}

                {step === 2 && (
                  <>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => setStep(1)}
                      disabled={isPending}
                      className="text-xs"
                    >
                      {ADD_CAMERA_COPY.BACK_TO_CAMERA}
                    </Button>
                    <Button
                      type="button"
                      variant="default"
                      onClick={handleContinueToStreams}
                      disabled={isPending}
                      className="text-xs"
                    >
                      {ADD_CAMERA_COPY.CONTINUE_TO_STREAMS}
                    </Button>
                  </>
                )}

                {step === 3 && (
                  <>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => setStep(2)}
                      disabled={isPending}
                      className="text-xs"
                    >
                      {ADD_CAMERA_COPY.BACK_TO_DETAILS}
                    </Button>
                    <Button
                      type="submit"
                      variant="default"
                      disabled={isPending}
                      className="text-xs"
                    >
                      {isPending && <Spinner className="mr-2 h-4 w-4" />}
                      {ADD_CAMERA_COPY.ADD_CAMERA_BUTTON}
                    </Button>
                  </>
                )}
              </div>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Discard Confirmation Alert Dialog */}
      <AlertDialog
        open={showDiscardDialog || blocker.state === "blocked"}
        onOpenChange={(open) => {
          if (!open) handleKeepEditing();
        }}
      >
        <AlertDialogContent className="sm:max-w-md">
          <AlertDialogHeader>
            <AlertDialogTitle>{ADD_CAMERA_COPY.DISCARD_TITLE}</AlertDialogTitle>
            <AlertDialogDescription>
              {ADD_CAMERA_COPY.DISCARD_BODY}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={handleKeepEditing}
            >
              {ADD_CAMERA_COPY.KEEP_EDITING_BUTTON}
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={handleConfirmDiscard}
            >
              {ADD_CAMERA_COPY.DISCARD_BUTTON}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
