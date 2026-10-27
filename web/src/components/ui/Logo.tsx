import Image from "next/image";

// Version claire sur fond sombre (thème par défaut), version sombre sur fond clair.
export function Logo({ size = 32, onLight = false }: { size?: number; onLight?: boolean }) {
  return (
    <Image
      src={onLight ? "/logo-dark.png" : "/logo-light.png"}
      alt="Synapse"
      width={size}
      height={size}
      priority
    />
  );
}
