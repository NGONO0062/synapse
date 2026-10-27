import type { ReactNode } from "react";
import { TYPE_LABELS, type TaskType } from "@/lib/domain";
import styles from "./Tag.module.css";

export type TagTone = "ai" | "human" | "error" | "warn" | "neutral";

export function Tag({ tone, children }: { tone: TagTone; children: ReactNode }) {
  return <span className={`${styles.tag} ${styles[tone]}`}>{children}</span>;
}

const TYPE_TONES: Record<TaskType, TagTone> = {
  FEATURE: "ai",
  BUGFIX: "error",
  DOC: "neutral",
};

export function TypeTag({ type }: { type: TaskType }) {
  return <Tag tone={TYPE_TONES[type]}>{TYPE_LABELS[type]}</Tag>;
}
