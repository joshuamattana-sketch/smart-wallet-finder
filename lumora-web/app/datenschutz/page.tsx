import type { Metadata } from "next";
import { LegalShell } from "@/components/legal/LegalShell";
import { OPERATOR, PROCESSORS } from "@/lib/site";

export const metadata: Metadata = {
  title: "Datenschutz",
  description:
    "Privacy policy for Lumora: what data we collect and why (Swiss revDSG / GDPR).",
};

// LM77A — Datenschutzerklärung. Swiss operator (revDSG / nDSG) whose site also
// reaches EU visitors, so the GDPR applies extraterritorially (Art. 3(2) GDPR):
// this policy names both regimes. Template scaffold — must be reviewed by a
// lawyer and kept in sync with the actual data flows in code.
export default function DatenschutzPage() {
  return (
    <LegalShell
      title="Datenschutzerklärung"
      subtitle="Privacy policy under the Swiss Data Protection Act (revDSG) and, for EU visitors, the GDPR. We keep data collection to the minimum needed to run a private beta."
    >
      <h2>1. Controller (Verantwortlicher)</h2>
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
      <p>
        Email: <a href={`mailto:${OPERATOR.email}`}>{OPERATOR.email}</a>
      </p>

      <h2>2. What we collect &amp; why</h2>

      <h3>Waitlist email</h3>
      <p>
        When you join the waitlist, we store the <strong>email address</strong> you submit, plus the
        time of submission. Purpose: to contact you about private-beta access. This is based on{" "}
        <strong>your consent</strong>, given when you submit the form (and, for EU visitors,
        Art. 6(1)(a) GDPR). You can withdraw it at any time (see section 7).
      </p>

      <h3>Invite code &amp; access cookie</h3>
      <p>
        When you redeem an invite code, we set one essential cookie (<code>lumora_access</code>) so
        the gated terminal knows you are an approved beta user. It contains a signed expiry value
        only (no tracking, no personal data) and expires after 30 days. As a strictly necessary
        cookie it does not require prior consent. For EU visitors the legal basis is our legitimate
        interest in securing the private beta (Art. 6(1)(f) GDPR).
      </p>

      <h3>Analytics (Google Analytics 4) — only with your consent</h3>
      <p>
        We use Google Analytics 4 to understand how the site is used. <strong>Nothing loads and no
        Google cookie is set until you click &ldquo;Akzeptieren&rdquo;</strong> in the consent
        banner; declining is just as easy and is the default. Your choice is stored locally
        (<code>lumora_consent_v1</code> in your browser). If you consent, Google sets analytics
        cookies and processes your usage data and IP address (IP handling is truncated/anonymised by
        Google). Basis: your consent (for EU visitors, Art. 6(1)(a) GDPR). Withdraw any time by
        clearing the stored choice or contacting us. Provider: {PROCESSORS.analytics}.
      </p>

      <h3>Server logs</h3>
      <p>
        Our hosting provider may process technical access data (IP address, timestamp, user agent)
        to deliver and secure the site. Basis: legitimate interest in a secure, functioning service
        (for EU visitors, Art. 6(1)(f) GDPR).
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
        <li>
          <strong>Analytics:</strong> {PROCESSORS.analytics}
        </li>
      </ul>

      <h2>4. Transfers abroad</h2>
      <p>
        Some providers process data outside Switzerland and the EU/EEA (e.g. in the USA). Such
        transfers are safeguarded by the EU Standard Contractual Clauses with the Swiss addendum, or
        by the provider&rsquo;s certification under the EU–US / Swiss–US Data Privacy Framework, or
        an equivalent mechanism recognised under the revDSG and the GDPR.
      </p>

      <h2>5. Retention</h2>
      <p>
        We keep waitlist emails until the beta ends or you ask us to delete yours, whichever comes
        first. The access cookie expires automatically after 30 days. Analytics data is retained for
        the period configured in Google Analytics.
      </p>

      <h2>6. No automated decision-making &amp; no profiling</h2>
      <p>
        The market &ldquo;reads&rdquo; shown in the product are not based on your personal data and
        do not profile you. We do not sell or share your data for marketing.
      </p>

      <h2>7. Your rights</h2>
      <p>
        Under the Swiss revDSG (and, for EU visitors, the GDPR) you have the right to:
      </p>
      <ul>
        <li>access the personal data we hold about you (Art. 25 revDSG / Art. 15 GDPR);</li>
        <li>rectification and erasure (Art. 32 revDSG / Art. 16–17 GDPR);</li>
        <li>restriction of processing and data portability (Art. 20 GDPR);</li>
        <li>object to processing based on legitimate interest (Art. 21 GDPR);</li>
        <li>withdraw consent at any time, without affecting prior processing;</li>
        <li>
          lodge a complaint with a supervisory authority: in Switzerland the Federal Data Protection
          and Information Commissioner (EDÖB), Feldeggweg 1, 3003 Bern; in the EU your local data
          protection authority.
        </li>
      </ul>
      <p>
        To exercise any of these, email{" "}
        <a href={`mailto:${OPERATOR.email}`}>{OPERATOR.email}</a>.
      </p>

      <h2>8. Changes</h2>
      <p>
        We may update this policy as the product evolves. The current version always lives at this
        URL; the date below reflects the last change.
      </p>
    </LegalShell>
  );
}
