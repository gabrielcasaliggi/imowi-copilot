import { redirect } from "next/navigation";

/** Redirect de servidor: no depende de hidratar JS (evita pantalla "Cargando…" si fallan chunks). */
export default function HomePage() {
  redirect("/login");
}
