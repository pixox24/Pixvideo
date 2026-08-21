import React from "react";

interface VideoPreviewProps {
  src: string;
  poster?: string;
  className?: string;
}

export const VideoPreview: React.FC<VideoPreviewProps> = ({ src, poster, className = "" }) => {
  return (
    <div
      className={[
        "ui-stage aspect-square w-full",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <video src={src} controls poster={poster} className="h-full w-full object-contain" />
    </div>
  );
};
