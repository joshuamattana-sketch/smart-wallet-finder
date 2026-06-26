import type { Metadata } from "next";
import { LegalShell } from "@/components/legal/LegalShell";

export const metadata: Metadata = {
  title: "Risk & Terms",
  description:
    "Risk disclosure and terms of use for Lumora. Informational market context only, not financial advice.",
};

// LM77A — Risk disclosure + light terms of use. The single linkable home for the
// "not financial advice" anchor that the footer points to from every screen.
export default function RiskPage() {
  return (
    <LegalShell
      title="Risk Disclosure & Terms"
      subtitle="Please read this before using Lumora. By using the product you accept these terms."
    >
      <h2>1. Informational only, not financial advice</h2>
      <p>
        Lumora is an <strong>informational market-intelligence tool</strong>. The data, liquidity
        maps, whale flow, scores, and &ldquo;reads&rdquo; (LONG / SHORT / NEUTRAL, etc.) it displays
        are a structural summary of market conditions. They are <strong>not</strong> financial,
        investment, trading, tax, or legal advice, not a recommendation or solicitation to buy or
        sell any asset, and not a prediction of future prices.
      </p>

      <h2>2. No guaranteed outcomes</h2>
      <p>
        Trading and investing in crypto assets carries substantial risk, including the total loss of
        capital. Nothing in Lumora guarantees any result. Any performance figures or targets shown
        (for example an aspirational bot target) are illustrative goals, <strong>not</strong>{" "}
        forecasts or promises. You are solely responsible for your own decisions and should consult a
        licensed professional before trading.
      </p>

      <h2>3. Demo &amp; beta data</h2>
      <p>
        Lumora is in private beta. Many surfaces show <strong>demo, mock, or fixture data</strong>{" "}
        for illustration, clearly labelled as such. Live integrations are rolling out gradually. Do
        not rely on any number in the product as a real-time market quote unless it is explicitly
        marked live and fresh.
      </p>

      <h2>4. Availability</h2>
      <p>
        The service is provided &ldquo;as is&rdquo; and &ldquo;as available&rdquo; during beta,
        without warranty of uptime, accuracy, or fitness for a particular purpose. We may change,
        suspend, or discontinue any part of it at any time.
      </p>

      <h2>5. Acceptable use</h2>
      <p>
        Access during private beta is personal and invite-based. Do not share invite codes, scrape
        the service, attempt to bypass the access gate, or resell access without permission.
      </p>

      <h2>6. Liability</h2>
      <p>
        To the extent permitted by law, the operator is not liable for any loss arising from your
        use of, or reliance on, the information provided by Lumora. Mandatory statutory liability
        (e.g. for intent or gross negligence) remains unaffected.
      </p>

      <h2>7. Contact</h2>
      <p>
        Operator and contact details are listed in our <a href="/impressum">Impressum</a>. How we
        handle data is described in our <a href="/datenschutz">Datenschutzerklärung</a>.
      </p>
    </LegalShell>
  );
}
