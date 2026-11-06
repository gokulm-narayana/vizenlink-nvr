import { z } from "zod";

export const addCameraSchema = z
  .object({
    // Step 1: Camera
    serial: z
      .string()
      .min(1, "Serial number is required")
      .max(64, "Serial number cannot exceed 64 characters")
      .regex(/^[A-Za-z0-9._-]+$/, "Only letters, numbers, '.', '_', and '-' are allowed")
      .refine((val) => val.trim().toLowerCase() !== "add", {
        message: "Serial cannot be 'add'",
      }),
    host: z.string().min(1, "IP address or hostname is required"),
    https_port: z.number().int().min(1).max(65535),
    username: z.string().min(1, "Username is required"),
    password: z.string().min(1, "Password is required"),

    // Step 2: Details
    name: z.string().optional(),
    location: z.string().optional(),
    group_tag: z.string().optional(),

    // Step 3: Streams
    main_scheme: z.enum(["rtsp", "rtsps"]),
    main_port: z.number().int().min(1).max(65535),
    main_path: z.string().min(1, "Main stream path is required"),
    main_codec: z.string(),
    main_width: z.number().int().min(1),
    main_height: z.number().int().min(1),
    main_transport: z.string(),
    main_profile_token: z.string(),
    main_venc_token: z.string(),

    has_sub_stream: z.boolean(),
    sub_scheme: z.enum(["rtsp", "rtsps"]),
    sub_port: z.number().int().min(1).max(65535),
    sub_path: z.string(),
    sub_codec: z.string(),
    sub_width: z.number().int().min(1),
    sub_height: z.number().int().min(1),
    sub_transport: z.string(),
    sub_profile_token: z.string(),
    sub_venc_token: z.string(),
  })
  .superRefine((data, ctx) => {
    if (data.has_sub_stream && (!data.sub_path || data.sub_path.trim() === "")) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Enter the camera's sub stream path.",
        path: ["sub_path"],
      });
    }
  });

export type AddCameraFormValues = z.infer<typeof addCameraSchema>;

export interface StreamInputPayload {
  role: string;
  profile_token: string;
  profile_name: string;
  venc_token: string;
  codec: string;
  width: number;
  height: number;
  transport: string;
  scheme: string;
  port: number;
  path: string;
  source: string;
  sub_is_main: boolean;
}

export interface CameraCreateRequestPayload {
  serial: string;
  host: string;
  https_port: number;
  username: string;
  password: string;
  name: string;
  location: string;
  group_tag: string;
  streams: StreamInputPayload[];
}

export function toCreateRequest(values: AddCameraFormValues): CameraCreateRequestPayload {
  const serial = values.serial.trim();
  const name = values.name && values.name.trim() !== "" ? values.name.trim() : serial;
  const location =
    values.location && values.location.trim() !== ""
      ? values.location.trim()
      : "Default";
  const group_tag =
    values.group_tag && values.group_tag.trim() !== ""
      ? values.group_tag.trim()
      : "default";

  const streams: StreamInputPayload[] = [
    {
      role: "main",
      profile_token: values.main_profile_token || "Profile_1",
      profile_name: "MainStream",
      venc_token: values.main_venc_token || "VideoEncoder_1",
      codec: values.main_codec || "H264",
      width: Number(values.main_width) || 1920,
      height: Number(values.main_height) || 1080,
      transport: values.main_transport || "tcp",
      scheme: values.main_scheme || "rtsp",
      port: Number(values.main_port) || 554,
      path: values.main_path || "/stream1",
      source: "onvif_fallback",
      sub_is_main: false,
    },
  ];

  if (values.has_sub_stream) {
    streams.push({
      role: "sub",
      profile_token: values.sub_profile_token || "Profile_2",
      profile_name: "SubStream",
      venc_token: values.sub_venc_token || "VideoEncoder_2",
      codec: values.sub_codec || "H264",
      width: Number(values.sub_width) || 1920,
      height: Number(values.sub_height) || 1080,
      transport: values.sub_transport || "tcp",
      scheme: values.sub_scheme || "rtsp",
      port: Number(values.sub_port) || 554,
      path: values.sub_path,
      source: "onvif_fallback",
      sub_is_main: false,
    });
  }

  return {
    serial,
    host: values.host.trim(),
    https_port: Number(values.https_port) || 443,
    username: values.username.trim(),
    password: values.password,
    name,
    location,
    group_tag,
    streams,
  };
}
