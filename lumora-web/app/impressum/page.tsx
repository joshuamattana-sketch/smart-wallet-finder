import type { Metadata } from "next";
import { LegalShell } from "@/components/legal/LegalShell";
import { OPERATOR } from "@/lib/site";

export const metadata: Metadata = {
  title: "Impressum",
  description: "Legal notice and operator information for Lumora.",
};

// LM77A — Impressum / legal notice. Swiss operator → UWG Art. 3 Abs. 1 lit. s
// (not the German DDG §5). Values come from OPERATOR in lib/site.ts. Until
// filled they render as visible placeholders and the shell shows a warning
// banner.
export default function ImpressumPage() {
  return (
    <LegalShell
      title="Impressum"
      subtitle="Legal notice / Angaben gemäss Art. 3 Abs. 1 lit. s UWG."
    >
      <h2>Operator (Betreiber)</h2>
      <address>
        {OPERATOR.name}
        {"\n"}
        {OPERATOR.street && (
          <>
            {OPERATOR.street}
            {"\n"}
          </>
        )}
        {OPERATOR.city}
        {"\n"}
        {OPERATOR.country}
      </address>

      {OPERATOR.representedBy && (
        <>
          <h2>Represented by (Vertreten durch)</h2>
          <p>{OPERATOR.representedBy}</p>
        </>
      )}

      <h2>Contact (Kontakt)</h2>
      <p>
        Email:{" "}
        <a href={`mailto:${OPERATOR.email}`}>{OPERATOR.email}</a>
        {OPERATOR.phone && (
          <>
            <br />
            Phone: {OPERATOR.phone}
          </>
        )}
      </p>

      {(OPERATOR.registerCourt || OPERATOR.vatId) && (
        <>
          <h2>Register &amp; VAT</h2>
          <p>
            {OPERATOR.registerCourt && (
              <>
                Register: {OPERATOR.registerCourt}
                <br />
              </>
            )}
            {OPERATOR.vatId && <>VAT ID (USt-IdNr.): {OPERATOR.vatId}</>}
          </p>
        </>
      )}

      <h2>Responsible for content (Inhaltlich verantwortlich)</h2>
      <p>{OPERATOR.name}, address as above.</p>

      <h2>Disclaimer</h2>
      <p>
        Lumora is an informational market-intelligence tool. It is not financial, investment, or
        trading advice and provides no guaranteed outcomes. See our{" "}
        <a href="/risk">Risk &amp; Terms</a> page.
      </p>
    </LegalShell>
  );
}
