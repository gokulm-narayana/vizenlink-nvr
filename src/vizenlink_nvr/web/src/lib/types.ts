export interface CameraInfo {
  serial: string;
  name: string;
  state: string;
  [key: string]: any;
}

export interface CameraOption {
  serial: string;
  name: string;
  [key: string]: any;
}

export type ViewMode = "simple" | "advanced";
