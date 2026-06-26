import type { Metadata } from "next";
import { LegalShell } from "@/components/legal/LegalShell";
import { OPERATOR, PROCESSORS } from "@/lib/site";

export const metadata: Metadata = {
  title: "Datenschutz",
  description: "Privacy policy for Lumora: what data we collect and why (GDPR / DSGVO).",
};

// LM77A — Datenschutzerklärung (GDPR Art. 13). Template scaffold — must be
// reviewed by a lawyer and kept in sync with the actual data flows.
export default function DatenschutzPage() {
  return (
    <LegalShell
      title="Datenschutzerklärung"
      subtitle="Privacy policy under the GDPR / DSGVO. We keep data collection to the minimum needed to run a private beta."
    >
      <h2>1. Controller (Verantwortlicher)</h2>
      <address>
        {OPERATOR.name}
        {"\n"}
        {OPERATOR.street}
        {"\n"}
        {OPERATOR.city}
        {"\n"}
        {OPERATOR.country}
      </address>
      <p>
        Email: <a href={`mailto:${OPERATOR.email}`}>{OPERATOR.email}</a>
      </p>

      <h2>2. What we collect &amp; why</h2>

      <h3>Waitlist email</h3>
      <p>
        When you join the waitlist, we store the <strong>email address</strong> you submit, plus the
        time of submission. Purpose: to contact you about private-beta access. Legal basis:{" "}
        <strong>your consent</strong> (Art. 6(1)(a) GDPR), given when you submit the form. You can
        withdraw it at any time (see section 6).
      </p>

      <h3>Invite code &amp; access cookie</h3>
      <p>
        When you redeem an invite code, we set one essential cookie (<code>lumora_access</code>) so
        the gated terminal knows you are an approved beta user. It contains a signed expiry value
        only (no tracking, no personal data) and expires after 30 days. Legal basis: our
        legitimate interest in securing the private beta (Art. 6(1)(f) GDPR); as a strictly
        necessary cookie it does not require prior consent (§ 25(2) TDDDG). We do not use analytics,
        advertising, or tracking cookies.
      </p>

      <h3>Server logs</h3>
      <p>
        Our hosting provider may process technical access data (IP address, timestamp, user agent)
        to deliver and secure the site. Legal basis: legitimate interest (Art. 6(1)(f) GDPR).
      </p>

      <h2>3. Processors &amp; hosting</h2>
      <p>We use the following service providers, bound by data-processing agreements:</p>
      <ul>
        <li>
          <strong>Hosting:</strong> {PROCESSORS.host}
        </li>
        <li>
          <strong>Database:</strong> {PROCESSORS.database}
        </li>
      </ul>
      <p>
        Where a processor is located outside the EU/EEA, the transfer is safeguarded by the EU
        Standard Contractual Clauses or an equivalent mechanism.
      </p>

      <h2>4. Retention</h2>
      <p>
        We keep waitlist emails until the beta ends or you ask us to delete yours, whichever comes
        first. The access cookie expires automatically after 30 days.
      </p>

      <h2>5. No automated decision-making &amp; no profiling</h2>
      <p>
        The market &ldquo;reads&rdquo; shown in the product are not based on your personal data and
        do not profile you. We do not sell or share your data for marketing.
      </p>

      <h2>6. Your rights</h2>
      <p>Under the GDPR you have the right to:</p>
      <ul>
        <li>access the personal data we hold about you (Art. 15);</li>
        <li>rectification (Art. 16) and erasure (Art. 17);</li>
        <li>restriction of processing (Art. 18) and data portability (Art. 20);</li>
        <li>object to processing based on legitimate interest (Art. 21);</li>
        <li>withdraw consent at any time, without affecting prior processing (Art. 7(3));</li>
        <li>
          lodge a complaint with a supervisory authority (Art. 77), e.g. your local
          Landesdatenschutzbehörde.
        </li>
      </ul>
      <p>
        To exercise any of these, email{" "}
        <a href={`mailto:${OPERATOR.email}`}>{OPERATOR.email}</a>.
      </p>

      <h2>7. Changes</h2>
      <p>
        We may update this policy as the product evolves. The current version always lives at this
        URL; the date below reflects the last change.
      </p>
    </LegalShell>
  );
}
