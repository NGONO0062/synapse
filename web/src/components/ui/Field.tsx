import type { InputHTMLAttributes, ReactNode } from "react";
import styles from "./Field.module.css";

type Props = InputHTMLAttributes<HTMLInputElement> & {
  id: string;
  label: string;
  aside?: ReactNode; // lien ou action à droite du libellé
};

export function Field({ id, label, aside, className, ...rest }: Props) {
  return (
    <div className={styles.field}>
      <div className={styles.labelRow}>
        <label htmlFor={id} className={styles.label}>
          {label}
        </label>
        {aside}
      </div>
      <input id={id} className={[styles.input, className].filter(Boolean).join(" ")} {...rest} />
    </div>
  );
}
