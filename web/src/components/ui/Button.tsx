import type { ButtonHTMLAttributes } from "react";
import styles from "./Button.module.css";

// human : décision humaine (vert, réservé). primary : action principale. outline : secondaire.
export type ButtonVariant = "human" | "primary" | "outline";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  block?: boolean;
};

export function Button({ variant = "outline", block = false, className, type = "button", ...rest }: Props) {
  const classes = [styles.button, styles[variant], block && styles.block, className].filter(Boolean).join(" ");
  return <button type={type} className={classes} {...rest} />;
}
