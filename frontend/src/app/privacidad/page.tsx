import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Política de privacidad — EKO-Asistente",
  description:
    "Cómo Cooperativa Batán y Ecolan tratan los datos de la app EKO-Asistente y del portal de soporte.",
};

export default function PrivacidadPage() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-12 text-slate-200">
      <p className="text-xs font-medium tracking-wide text-[#2298A6]">EKO-Asistente</p>
      <h1 className="mt-2 text-3xl font-semibold text-slate-50">Política de privacidad</h1>
      <p className="mt-2 text-sm text-slate-400">Última actualización: 19 de agosto de 2026</p>

      <div className="mt-8 space-y-6 text-sm leading-6 text-slate-300">
        <section>
          <h2 className="text-lg font-semibold text-slate-50">Quién es responsable</h2>
          <p className="mt-2">
            La app <strong>EKO-Asistente</strong> y el portal de soporte son operados por{" "}
            <strong>Cooperativa Batán</strong> junto con <strong>Ecolan</strong>, para que los
            socios consulten sobre su servicio (internet y móvil) sin pasar por WhatsApp.
          </p>
          <p className="mt-2">
            Contacto:{" "}
            <a className="text-[#2298A6] underline" href="mailto:admin@ecolan.com">
              admin@ecolan.com
            </a>
            . Sitio:{" "}
            <a className="text-[#2298A6] underline" href="https://ibot.ecolan.com/portal">
              ibot.ecolan.com/portal
            </a>
            .
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-slate-50">Qué datos usamos</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            <li>DNI, para verificar que sos socio o abonado.</li>
            <li>Email o teléfono de contacto (enmascarado) para enviar el código OTP.</li>
            <li>PIN que elijas, guardado solo como hash (no en texto claro).</li>
            <li>Mensajes del chat de soporte, incluidas consultas por voz transcritas.</li>
            <li>Identificador del dispositivo si habilitás notificaciones (token de push).</li>
          </ul>
          <p className="mt-2">
            El padrón de socios (nombre, servicio, deuda) ya existe en la cooperativa. La app no
            crea ese padrón: solo lo consulta para atenderte.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-slate-50">Para qué</h2>
          <p className="mt-2">
            Identificarte, responder consultas de soporte, derivar a un agente cuando hace falta y
            avisarte si hay un incidente de red. No vendemos datos. No usamos publicidad en la app.
            No compartimos el chat con terceros ajenos a la operación de soporte, salvo obligación
            legal.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-slate-50">Dónde se procesan</h2>
          <p className="mt-2">
            Los datos viajan cifrados (HTTPS) hacia los servidores de la cooperativa en{" "}
            <code className="text-slate-100">ibot.ecolan.com</code>. El chat puede pasar por un
            modelo de lenguaje contratado para redactar la respuesta automática; no se usa para
            entrenar modelos propios de publicidad.
          </p>
        </section>

        <section id="eliminar-cuenta">
          <h2 className="text-lg font-semibold text-slate-50">Cómo borrar tus datos de la app</h2>
          <p className="mt-2">
            En EKO-Asistente, con la sesión iniciada: <strong>Eliminar datos</strong>. Eso borra el
            PIN, los dispositivos registrados y el vínculo de la app. El padrón de socio de la
            cooperativa (servicio, facturación) no se elimina: es el registro de tu cuenta de
            socio, no de la app.
          </p>
          <p className="mt-2">
            También podés escribir a{" "}
            <a className="text-[#2298A6] underline" href="mailto:admin@ecolan.com">
              admin@ecolan.com
            </a>{" "}
            y pedir la baja de los datos de la app.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-slate-50">Permisos del celular</h2>
          <p className="mt-2">
            El micrófono es opcional y solo se usa si grabás una consulta por voz. Internet es
            necesario para el chat. No pedimos ubicación ni acceso a contactos.
          </p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-slate-50">Tus derechos</h2>
          <p className="mt-2">
            Según la Ley 25.326 de Protección de Datos Personales (Argentina) podés pedir acceso,
            rectificación o supresión de los datos que trata la app, escribiendo a{" "}
            <a className="text-[#2298A6] underline" href="mailto:admin@ecolan.com">
              admin@ecolan.com
            </a>
            .
          </p>
        </section>
      </div>

      <p className="mt-10 text-sm">
        <Link href="/portal" className="text-[#2298A6] underline">
          Volver al portal
        </Link>
      </p>
    </main>
  );
}
