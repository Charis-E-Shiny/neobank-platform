import { useEffect, useState } from "react";
import { api, getStoredApiKey, money, storeApiKey } from "./api.js";

const NAV = [
  {
    id: "accounts",
    label: "Accounts",
    title: "Accounts",
    subtitle: "Open accounts, post deposits and transfers, and review statements.",
  },
  {
    id: "authorize",
    label: "Card authorization",
    title: "Card authorization",
    subtitle: "Score a card transaction for fraud risk before it settles.",
  },
  {
    id: "credit",
    label: "Credit",
    title: "Credit decisioning",
    subtitle: "Assess a credit application with a scorecard and reason codes.",
  },
  {
    id: "decisions",
    label: "Decision log",
    title: "Decision log",
    subtitle: "Audit trail of every fraud and credit decision, with inputs, scores and model versions.",
  },
];

// Converts a major-unit amount typed by the user (e.g. "12.50") to integer minor units (1250).
const toMinor = (value) => Math.round(Number(value) * 100);

export default function App() {
  const [page, setPage] = useState("accounts");
  const [apiKey, setApiKey] = useState(getStoredApiKey());
  const current = NAV.find((item) => item.id === page);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">N</span>
          <div>
            <div className="brand-name">Neobank</div>
            <div className="brand-sub">Operator console</div>
          </div>
        </div>

        <nav className="nav" aria-label="Main">
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`nav-item${page === item.id ? " active" : ""}`}
              aria-current={page === item.id ? "page" : undefined}
              onClick={() => setPage(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <div className="sidebar-foot">
          <label className="field">
            <span className="field-label">API key</span>
            <input
              type="password"
              autoComplete="off"
              value={apiKey}
              placeholder="Optional in local development"
              onChange={(e) => {
                setApiKey(e.target.value);
                storeApiKey(e.target.value.trim());
              }}
            />
            <span className="hint">Stored in this browser only.</span>
          </label>
        </div>
      </aside>

      <main className="main">
        <header className="page-head">
          <h1>{current.title}</h1>
          <p>{current.subtitle}</p>
        </header>

        {page === "accounts" && <AccountsPage />}
        {page === "authorize" && <AuthorizePage />}
        {page === "credit" && <CreditPage />}
        {page === "decisions" && <DecisionsPage />}
      </main>
    </div>
  );
}

/* ---------- shared pieces ---------- */

function Field({ label, hint, children }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="hint">{hint}</span>}
    </label>
  );
}

function SubmitButton({ pending, children }) {
  return (
    <button type="submit" className="btn primary" disabled={pending}>
      {pending ? "Working…" : children}
    </button>
  );
}

function Notice({ state }) {
  if (!state) return null;
  return (
    <div role="status" className={`notice ${state.error ? "error" : "success"}`}>
      {state.text}
    </div>
  );
}

// Runs an async action, tracking its result message and whether it is still in flight.
function useAction() {
  const [state, setState] = useState(null);
  const [pending, setPending] = useState(false);

  const run = async (fn, successText) => {
    setState(null);
    setPending(true);
    try {
      const result = await fn();
      setState({ text: typeof successText === "function" ? successText(result) : successText });
      return result;
    } catch (err) {
      setState({ error: true, text: err.message });
      return null;
    } finally {
      setPending(false);
    }
  };

  return [state, run, pending];
}

function Badge({ outcome }) {
  return <span className={`badge ${outcome.toLowerCase()}`}>{outcome}</span>;
}

function Meter({ value }) {
  const pct = Math.min(Math.max(value * 100, 0), 100);
  return (
    <div className="meter" role="img" aria-label={`${pct.toFixed(1)} percent`}>
      <span style={{ width: `${pct}%` }} />
    </div>
  );
}

/* ---------- accounts ---------- */

function AccountsPage() {
  const [form, setForm] = useState({ id: "", owner_name: "", currency: "USD" });
  const [opened, runOpen, openPending] = useAction();

  const [deposit, setDeposit] = useState({ account: "", amount: "" });
  const [depositMsg, runDeposit, depositPending] = useAction();

  const [transfer, setTransfer] = useState({ from: "", to: "", amount: "", description: "" });
  const [transferMsg, runTransfer, transferPending] = useAction();

  const [lookupId, setLookupId] = useState("");
  const [loaded, setLoaded] = useState(null); // id of the account currently shown
  const [account, setAccount] = useState(null);
  const [statement, setStatement] = useState([]);
  const [lookupMsg, runLookup, lookupPending] = useAction();

  const loadAccount = async (id) => {
    const enc = encodeURIComponent(id);
    const [a, s] = await Promise.all([
      api(`/accounts/${enc}`),
      api(`/accounts/${enc}/statement?limit=10`),
    ]);
    setAccount(a);
    setStatement(s);
    setLoaded(id);
    return a;
  };

  // After a movement of money, refresh the balance if that account is on screen.
  const refreshIfShown = (ids) => {
    if (loaded && ids.includes(loaded)) loadAccount(loaded).catch(() => {});
  };

  return (
    <section className="grid">
      <div className="card">
        <div className="card-head"><h2>Open an account</h2></div>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const a = await runOpen(() => api("/accounts", { method: "POST", body: form }), (r) => `Opened ${r.id}`);
            if (a) setForm({ id: "", owner_name: "", currency: "USD" });
          }}
        >
          <Field label="Account ID" hint="A unique reference, for example ACC-1001.">
            <input required value={form.id} onChange={(e) => setForm({ ...form, id: e.target.value })} />
          </Field>
          <Field label="Owner name">
            <input required value={form.owner_name} onChange={(e) => setForm({ ...form, owner_name: e.target.value })} />
          </Field>
          <Field label="Currency" hint="Three-letter ISO code.">
            <input
              required
              maxLength={3}
              value={form.currency}
              onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })}
            />
          </Field>
          <SubmitButton pending={openPending}>Open account</SubmitButton>
        </form>
        <Notice state={opened} />
      </div>

      <div className="card">
        <div className="card-head"><h2>Deposit</h2></div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const reference = `dep-${Date.now()}`;
            runDeposit(
              () => api(`/accounts/${encodeURIComponent(deposit.account)}/deposits`, {
                method: "POST",
                body: { reference, amount_minor: toMinor(deposit.amount) },
              }),
              "Deposit recorded",
            ).then((r) => r && refreshIfShown([deposit.account]));
          }}
        >
          <Field label="Account ID">
            <input required value={deposit.account} onChange={(e) => setDeposit({ ...deposit, account: e.target.value })} />
          </Field>
          <Field label="Amount">
            <input
              required
              type="number"
              min="0.01"
              step="0.01"
              inputMode="decimal"
              value={deposit.amount}
              onChange={(e) => setDeposit({ ...deposit, amount: e.target.value })}
            />
          </Field>
          <SubmitButton pending={depositPending}>Post deposit</SubmitButton>
        </form>
        <Notice state={depositMsg} />
      </div>

      <div className="card">
        <div className="card-head"><h2>Transfer</h2></div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const reference = `tx-${Date.now()}`;
            runTransfer(
              () => api("/transfers", {
                method: "POST",
                body: {
                  reference,
                  from_account_id: transfer.from,
                  to_account_id: transfer.to,
                  amount_minor: toMinor(transfer.amount),
                  currency: "USD",
                  description: transfer.description,
                },
              }),
              (j) => `Transfer recorded (journal ${j.journal_id})`,
            ).then((r) => r && refreshIfShown([transfer.from, transfer.to]));
          }}
        >
          <div className="two">
            <Field label="From account">
              <input required value={transfer.from} onChange={(e) => setTransfer({ ...transfer, from: e.target.value })} />
            </Field>
            <Field label="To account">
              <input required value={transfer.to} onChange={(e) => setTransfer({ ...transfer, to: e.target.value })} />
            </Field>
          </div>
          <Field label="Amount" hint="Currency: USD.">
            <input
              required
              type="number"
              min="0.01"
              step="0.01"
              inputMode="decimal"
              value={transfer.amount}
              onChange={(e) => setTransfer({ ...transfer, amount: e.target.value })}
            />
          </Field>
          <Field label="Description (optional)">
            <input value={transfer.description} onChange={(e) => setTransfer({ ...transfer, description: e.target.value })} />
          </Field>
          <SubmitButton pending={transferPending}>Send transfer</SubmitButton>
        </form>
        <Notice state={transferMsg} />
      </div>

      <div className="card wide">
        <div className="card-head">
          <h2>Balance and statement</h2>
        </div>
        <form
          className="inline-form"
          onSubmit={(e) => {
            e.preventDefault();
            runLookup(() => loadAccount(lookupId.trim()), "Account loaded");
          }}
        >
          <Field label="Account ID">
            <input required value={lookupId} onChange={(e) => setLookupId(e.target.value)} />
          </Field>
          <SubmitButton pending={lookupPending}>Load account</SubmitButton>
        </form>
        <Notice state={lookupMsg} />

        {account && (
          <>
            <div className="balance-block">
              <div>
                <div className="muted">{account.owner_name}</div>
                <div className="mono">{loaded}</div>
              </div>
              <div className="balance">{money(account.balance_minor, account.currency)}</div>
            </div>

            {statement.length === 0 ? (
              <p className="empty">No transactions yet.</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Reference</th><th>Description</th><th className="num">Amount</th></tr>
                  </thead>
                  <tbody>
                    {statement.map((line) => (
                      <tr key={line.reference}>
                        <td className="mono">{line.reference}</td>
                        <td>{line.description}</td>
                        <td className={`num ${line.amount_minor < 0 ? "neg" : "pos"}`}>
                          {money(line.amount_minor, line.currency)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}

/* ---------- card authorization ---------- */

const CHANNELS = [
  { value: "pos", label: "Card present (POS)" },
  { value: "online", label: "Card not present (online)" },
  { value: "atm", label: "ATM" },
];

function AuthorizePage() {
  const [form, setForm] = useState({
    account_id: "", amount: "", merchant: "", mcc: "5411", channel: "pos", device_id: "",
  });
  const [decision, setDecision] = useState(null);
  const [result, run, pending] = useAction();

  return (
    <section className="grid">
      <div className="card">
        <div className="card-head"><h2>Transaction</h2></div>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const out = await run(
              () => api("/fraud/authorizations", {
                method: "POST",
                body: {
                  account_id: form.account_id,
                  amount_minor: toMinor(form.amount),
                  currency: "USD",
                  merchant: form.merchant,
                  mcc: form.mcc,
                  channel: form.channel,
                  device_id: form.device_id || null,
                },
              }),
              (d) => `Scored: ${d.outcome}`,
            );
            setDecision(out);
          }}
        >
          <Field label="Account ID">
            <input required value={form.account_id} onChange={(e) => setForm({ ...form, account_id: e.target.value })} />
          </Field>
          <div className="two">
            <Field label="Amount">
              <input
                required
                type="number"
                min="0.01"
                step="0.01"
                inputMode="decimal"
                value={form.amount}
                onChange={(e) => setForm({ ...form, amount: e.target.value })}
              />
            </Field>
            <Field label="MCC" hint="Four-digit merchant category code.">
              <input
                required
                pattern="\d{4}"
                inputMode="numeric"
                value={form.mcc}
                onChange={(e) => setForm({ ...form, mcc: e.target.value })}
              />
            </Field>
          </div>
          <Field label="Merchant">
            <input required value={form.merchant} onChange={(e) => setForm({ ...form, merchant: e.target.value })} />
          </Field>
          <Field label="Channel">
            <select value={form.channel} onChange={(e) => setForm({ ...form, channel: e.target.value })}>
              {CHANNELS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
          </Field>
          <Field label="Device ID (optional)">
            <input value={form.device_id} onChange={(e) => setForm({ ...form, device_id: e.target.value })} />
          </Field>
          <SubmitButton pending={pending}>Score authorization</SubmitButton>
        </form>
        <Notice state={result} />
      </div>

      {decision ? (
        <div className="card">
          <div className="card-head"><h2>Result</h2></div>
          <Badge outcome={decision.outcome} />
          <div className="stat">
            <span className="muted">Risk score</span>
            <strong>{(decision.score * 100).toFixed(1)}%</strong>
            <Meter value={decision.score} />
          </div>
          {decision.reasons.length > 0 && (
            <>
              <h3>Reasons</h3>
              <ul className="reasons">{decision.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            </>
          )}
          <p className="muted">Model {decision.model_version}</p>
        </div>
      ) : (
        <div className="card placeholder">
          <p className="muted">Submit a transaction to see the risk score and the reasons behind it.</p>
        </div>
      )}
    </section>
  );
}

/* ---------- credit ---------- */

function CreditPage() {
  const [form, setForm] = useState({
    applicant_id: "", income: "", monthly_debt: "", utilization: "0.1",
    delinquencies: "0", history: "5", inquiries: "0", requested: "",
  });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const [decision, setDecision] = useState(null);
  const [result, run, pending] = useAction();

  return (
    <section className="grid">
      <div className="card">
        <div className="card-head"><h2>Application</h2></div>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const out = await run(
              () => api("/credit/applications", {
                method: "POST",
                body: {
                  applicant_id: form.applicant_id,
                  annual_income_minor: toMinor(form.income),
                  monthly_debt_minor: toMinor(form.monthly_debt),
                  revolving_utilization: Number(form.utilization),
                  delinquencies_24m: Number(form.delinquencies),
                  credit_history_years: Number(form.history),
                  recent_inquiries_6m: Number(form.inquiries),
                  requested_minor: toMinor(form.requested),
                },
              }),
              (d) => `Assessed: ${d.outcome}`,
            );
            setDecision(out);
          }}
        >
          <Field label="Applicant reference">
            <input required value={form.applicant_id} onChange={set("applicant_id")} />
          </Field>
          <div className="two">
            <Field label="Annual income">
              <input required type="number" min="1" inputMode="decimal" value={form.income} onChange={set("income")} />
            </Field>
            <Field label="Monthly debt payments">
              <input required type="number" min="0" inputMode="decimal" value={form.monthly_debt} onChange={set("monthly_debt")} />
            </Field>
          </div>
          <div className="two">
            <Field label="Card utilization" hint="Between 0 and 1.">
              <input required type="number" min="0" max="1" step="0.01" value={form.utilization} onChange={set("utilization")} />
            </Field>
            <Field label="Credit history (years)">
              <input required type="number" min="0" step="0.5" value={form.history} onChange={set("history")} />
            </Field>
          </div>
          <div className="two">
            <Field label="Late payments, last 24 months">
              <input required type="number" min="0" value={form.delinquencies} onChange={set("delinquencies")} />
            </Field>
            <Field label="Credit inquiries, last 6 months">
              <input required type="number" min="0" value={form.inquiries} onChange={set("inquiries")} />
            </Field>
          </div>
          <Field label="Requested amount">
            <input required type="number" min="1" inputMode="decimal" value={form.requested} onChange={set("requested")} />
          </Field>
          <SubmitButton pending={pending}>Assess application</SubmitButton>
        </form>
        <Notice state={result} />
      </div>

      {decision ? (
        <div className="card">
          <div className="card-head"><h2>Decision</h2></div>
          <Badge outcome={decision.outcome} />
          <div className="stat">
            <span className="muted">Estimated probability of default</span>
            <strong>{(decision.probability_of_default * 100).toFixed(2)}%</strong>
            <Meter value={decision.probability_of_default} />
          </div>
          <div className="stat">
            <span className="muted">Approved amount</span>
            <strong>{money(decision.approved_amount_minor)}</strong>
          </div>
          {decision.reasons.length > 0 && (
            <>
              <h3>Reason codes</h3>
              <ul className="reasons">{decision.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            </>
          )}
          <p className="muted">Model {decision.model_version}</p>
        </div>
      ) : (
        <div className="card placeholder">
          <p className="muted">Submit an application to see the decision, reason codes and approved amount.</p>
        </div>
      )}
    </section>
  );
}

/* ---------- decision log ---------- */

function DecisionsPage() {
  const [kind, setKind] = useState("");
  const [rows, setRows] = useState([]);
  const [msg, run, pending] = useAction();

  const load = async () => {
    const data = await api(`/decisions?limit=100${kind ? `&kind=${kind}` : ""}`);
    setRows(data);
    return data;
  };

  // Load on open and whenever the filter changes.
  useEffect(() => {
    run(load, (data) => `${data.length} decision${data.length === 1 ? "" : "s"} loaded`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind]);

  return (
    <section className="card">
      <div className="toolbar">
        <Field label="Type">
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">All decisions</option>
            <option value="fraud">Card fraud</option>
            <option value="credit">Credit</option>
          </select>
        </Field>
        <button type="button" className="btn ghost" disabled={pending} onClick={() => run(load, (d) => `${d.length} loaded`)}>
          {pending ? "Loading…" : "Refresh"}
        </button>
      </div>
      <Notice state={msg} />

      {rows.length === 0 && !pending ? (
        <p className="empty">No decisions recorded yet.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>When</th><th>Type</th><th>Subject</th><th>Outcome</th>
                <th className="num">Score</th><th>Reasons</th><th>Model</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="nowrap">{new Date(r.created_at).toLocaleString()}</td>
                  <td>{r.kind === "fraud" ? "Card fraud" : "Credit"}</td>
                  <td className="mono">{r.subject_id}</td>
                  <td><Badge outcome={r.outcome} /></td>
                  <td className="num">{(r.score * 100).toFixed(1)}%</td>
                  <td>{r.reasons.join("; ") || "—"}</td>
                  <td className="mono muted">{r.model_version}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
