import type { ReactNode } from "react";
import { TYPE_LABELS, type TaskType } from "@/lib/domain";
import styles from "./Tag.module.css";

export type TagTone = "ai" | "human" | "error" | "warn" | "neutral";

export function Tag({ tone, small = false, children }: { tone: TagTone; small?: boolean; children: ReactNode }) {
  return <span className={[styles.tag, styles[tone], small && styles.small].filter(Boolean).join(" ")}>{children}</span>;
}

const TYPE_TONES: Record<TaskType, TagTone> = {
  FEATURE: "ai",
  BUGFIX: "error",
  DOC: "neutral",
};

export function TypeTag({ type, small = false }: { type: TaskType; small?: boolean }) {
  return (
    <Tag tone={TYPE_TONES[type]} small={small}>
      {TYPE_LABELS[type]}
    </Tag>
  );
}
