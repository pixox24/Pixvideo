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
        "aspect-square w-full overflow-hidden rounded border border-zinc-800 bg-black flex items-center justify-center",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <video src={src} controls poster={poster} className="h-full w-full object-contain" />
    </div>
  );
};
