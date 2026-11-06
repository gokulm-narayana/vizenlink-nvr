import React, { useState } from "react";
import { useNavigate } from "react-router";
import { XIcon, Download, Play, Trash2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { InlineError } from "@/components/InlineError";
import { formatDateTime, useSiteTimeZone } from "@/lib/time";
import { useCurrentUser } from "@/lib/queries";
import type { GalleryItem } from "./api";
import { useDeleteGalleryItem } from "./api";
import { formatDuration } from "./GalleryCard";
import { GALLERY_COPY } from "./copy";

export interface PreviewDialogProps {
  item: GalleryItem | null;
  cameraName?: string;
  isOpen: boolean;
  onClose: () => void;
  zone?: string;
}

export function formatFileSize(bytes: number): string {
  if (bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export const PreviewDialog: React.FC<PreviewDialogProps> = ({
  item,
  cameraName,
  isOpen,
  onClose,
  zone: zoneProp,
}) => {
  const navigate = useNavigate();
  const defaultZone = useSiteTimeZone();
  const zone = zoneProp || defaultZone;
  const user = useCurrentUser();

  const [showConfirm, setShowConfirm] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const deleteMutation = useDeleteGalleryItem();

  if (!item) return null;

  const isSnapshot = item.item_type === "snapshot";
  const mediaType = isSnapshot ? ("snapshot" as const) : ("clip" as const);
  const mediaUrl = `/api/v1/gallery/${item.id}/download`;
  const displayName = cameraName || item.camera_serial;
  const formattedTime = formatDateTime(item.captured_at, zone);
  const canDelete = user?.role === "owner" || user?.role === "operator";

  const handleOpenInPlayback = () => {
    onClose();
    void navigate(
      `/playback?camera=${encodeURIComponent(item.camera_serial)}&t=${encodeURIComponent(item.captured_at)}`
    );
  };

  const handleConfirmDelete = async () => {
    setDeleteError(null);
    try {
      await deleteMutation.mutateAsync(item.id);
      setShowConfirm(false);
      onClose();
    } catch {
      setShowConfirm(false);
      setDeleteError(GALLERY_COPY.DELETE_ERROR_MESSAGE(mediaType));
    }
  };

  return (
    <>
      <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
        <DialogContent
          showCloseButton={false}
          className="max-w-[960px] sm:max-w-4xl p-0 overflow-hidden flex flex-col bg-card"
        >
          {/* Header */}
          <DialogHeader className="flex flex-row items-center justify-between border-b border-border p-4">
            <DialogTitle className="text-sm font-semibold truncate pr-8" title={item.title}>
              {item.title}
            </DialogTitle>
            <Button
              aria-label={GALLERY_COPY.PREVIEW_CLOSE_LABEL}
              variant="ghost"
              size="icon"
              onClick={onClose}
              className="absolute top-2 right-2 h-8 w-8 z-20"
            >
              <XIcon className="h-4 w-4" />
              <span className="sr-only">{GALLERY_COPY.PREVIEW_CLOSE_LABEL}</span>
            </Button>
          </DialogHeader>

          {/* Delete Error Banner */}
          {deleteError && (
            <div className="p-4 pb-0">
              <InlineError
                message={deleteError}
                actionLabel={GALLERY_COPY.DELETE_ERROR_ACTION(mediaType)}
                onAction={handleConfirmDelete}
                pending={deleteMutation.isPending}
              />
            </div>
          )}

          {/* Media Player / Image */}
          <div className="relative aspect-video w-full bg-black flex items-center justify-center overflow-hidden">
            {isSnapshot ? (
              <img
                src={mediaUrl}
                alt={item.title}
                className="max-h-full max-w-full object-contain"
              />
            ) : (
              <video
                src={mediaUrl}
                controls
                autoPlay
                className="max-h-full max-w-full"
              />
            )}
          </div>

          {/* Metadata & Actions Footer */}
          <div className="flex flex-wrap items-center justify-between gap-4 border-t border-border p-4 bg-card">
            {/* Metadata Details */}
            <div className="flex flex-wrap items-center gap-4 text-xs font-normal text-muted-foreground">
              <div className="flex items-center gap-1">
                <span>{GALLERY_COPY.METADATA_CAMERA}:</span>
                <strong className="text-foreground">{displayName}</strong>
              </div>
              <div className="flex items-center gap-1">
                <span>{GALLERY_COPY.METADATA_TIME}:</span>
                <strong className="text-foreground">{formattedTime}</strong>
              </div>
              <div className="flex items-center gap-1">
                <span>{GALLERY_COPY.METADATA_FILE_SIZE}:</span>
                <strong className="text-foreground">{formatFileSize(item.file_size_bytes)}</strong>
              </div>
              {!isSnapshot && item.duration_seconds && (
                <div className="flex items-center gap-1">
                  <span>{GALLERY_COPY.METADATA_DURATION}:</span>
                  <strong className="text-foreground">{formatDuration(item.duration_seconds)}</strong>
                </div>
              )}
            </div>

            {/* Action Buttons */}
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                asChild
                className="h-8 gap-1.5 text-xs font-semibold"
              >
                <a href={mediaUrl} download={item.title}>
                  <Download className="h-3.5 w-3.5" />
                  <span>{isSnapshot ? GALLERY_COPY.DOWNLOAD_SNAPSHOT : GALLERY_COPY.DOWNLOAD_CLIP}</span>
                </a>
              </Button>

              <Button
                variant="secondary"
                size="sm"
                onClick={handleOpenInPlayback}
                className="h-8 gap-1.5 text-xs font-semibold"
              >
                <Play className="h-3.5 w-3.5" />
                <span>{GALLERY_COPY.OPEN_IN_PLAYBACK}</span>
              </Button>

              {canDelete && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowConfirm(true)}
                  className="h-8 gap-1.5 text-xs font-semibold text-destructive hover:text-destructive border-destructive/30"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  <span>{isSnapshot ? GALLERY_COPY.DELETE_SNAPSHOT : GALLERY_COPY.DELETE_CLIP}</span>
                </Button>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Alert Dialog */}
      <AlertDialog open={showConfirm} onOpenChange={setShowConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {GALLERY_COPY.DELETE_CONFIRM_TITLE(mediaType)}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {GALLERY_COPY.DELETE_CONFIRM_DESCRIPTION}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>
              {GALLERY_COPY.DELETE_CANCEL_ACTION(mediaType)}
            </AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={handleConfirmDelete}
            >
              {GALLERY_COPY.DELETE_CONFIRM_ACTION(mediaType)}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
};
