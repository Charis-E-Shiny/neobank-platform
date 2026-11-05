import { useState } from "react";
import { api, getStoredApiKey, money, storeApiKey } from "./api.js";

const TABS = ["Accounts", "Authorize", "Credit", "Decisions"];

export default function App() {
  const [tab, setTab] = useState("Accounts");
  const [apiKey, setApiKey] = useState(getStoredApiKey());

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">Neobank Platform</div>
        <label className="keybox">
          API key
          <input
            type="password"
            value={apiKey}
            placeholder="optional"
            onChange={(e) => {
              setApiKey(e.target.value);
              storeApiKey(e.target.value.trim());
            }}
          />
        </label>
      </header>

      <nav className="tabs">
        {TABS.map((name) => (
          <button key={name} className={tab === name ? "active" : ""} onClick={() => setTab(name)}>
            {name}
          </button>
        ))}
      </nav>

      <main>
        {tab === "Accounts" && <AccountsPanel />}
        {tab === "Authorize" && <AuthorizePanel />}
        {tab === "Credit" && <CreditPanel />}
        {tab === "Decisions" && <DecisionsPanel />}
      </main>
    </div>
  );
}

function Message({ state }) {
  if (!state) return null;
  return <p className={state.error ? "msg error" : "msg ok"}>{state.text}</p>;
}

function useAction() {
  const [state, setState] = useState(null);
  const run = async (fn, successText) => {
    setState(null);
    try {
      const result = await fn();
      setState({ text: typeof successText === "function" ? successText(result) : successText });
      return result;
    } catch (err) {
      setState({ error: true, text: err.message });
      return null;
    }
  };
  return [state, run];
}

function AccountsPanel() {
  const [created, runCreate] = useAction();
  const [account, setAccount] = useState(null);
  const [lookup, setLookup] = useState("");
  const [lookupMsg, runLookup] = useAction();
  const [transfer, runTransfer] = useAction();
  const [statement, setStatement] = useState([]);
  const [form, setForm] = useState({ id: "", owner_name: "", currency: "USD" });
  const [deposit, setDeposit] = useState({ account: "", amount: "" });
  const [pay, setPay] = useState({ from: "", to: "", amount: "", currency: "USD", description: "" });

  const refresh = async (id) => {
    const a = await api(`/accounts/${encodeURIComponent(id)}`);
    const s = await api(`/accounts/${encodeURIComponent(id)}/statement?limit=10`);
    setAccount(a);
    setStatement(s);
  };

  return (
    <section className="grid">
      <div className="card">
        <h2>Open an account</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            runCreate(() => api("/accounts", { method: "POST", body: form }), (a) => `Opened ${a.id}`);
          }}
        >
          <input required placeholder="Account id" value={form.id} onChange={(e) => setForm({ ...form, id: e.target.value })} />
          <input required placeholder="Owner name" value={form.owner_name} onChange={(e) => setForm({ ...form, owner_name: e.target.value })} />
          <input required maxLength={3} placeholder="Currency (USD)" value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })} />
          <button type="submit">Open</button>
        </form>
        <Message state={created} />
      </div>

      <div className="card">
        <h2>Balance and statement</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            runLookup(() => refresh(lookup), "Loaded");
          }}
        >
          <input required placeholder="Account id" value={lookup} onChange={(e) => setLookup(e.target.value)} />
          <button type="submit">Load</button>
        </form>
        <Message state={lookupMsg} />
        {account && (
          <>
            <p className="balance">{account.owner_name} · {money(account.balance_minor, account.currency)}</p>
            <table>
              <thead><tr><th>Reference</th><th>Description</th><th>Amount</th></tr></thead>
              <tbody>
                {statement.map((line) => (
                  <tr key={line.reference}>
                    <td>{line.reference}</td>
                    <td>{line.description}</td>
                    <td className={line.amount_minor < 0 ? "neg" : "pos"}>{money(line.amount_minor, line.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>

      <div className="card">
        <h2>Deposit</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const reference = `dep-${Date.now()}`;
            runCreate(
              () => api(`/accounts/${encodeURIComponent(deposit.account)}/deposits`, {
                method: "POST",
                body: { reference, amount_minor: Math.round(Number(deposit.amount) * 100) },
              }),
              "Deposit recorded",
            );
          }}
        >
          <input required placeholder="Account id" value={deposit.account} onChange={(e) => setDeposit({ ...deposit, account: e.target.value })} />
          <input required type="number" min="0.01" step="0.01" placeholder="Amount" value={deposit.amount} onChange={(e) => setDeposit({ ...deposit, amount: e.target.value })} />
          <button type="submit">Deposit</button>
        </form>
      </div>

      <div className="card">
        <h2>Transfer</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const reference = `tx-${Date.now()}`;
            runTransfer(
              () => api("/transfers", {
                method: "POST",
                body: {
                  reference,
                  from_account_id: pay.from,
                  to_account_id: pay.to,
                  amount_minor: Math.round(Number(pay.amount) * 100),
                  currency: pay.currency,
                  description: pay.description,
                },
              }),
              (j) => `Transfer recorded (journal ${j.journal_id})`,
            );
          }}
        >
          <input required placeholder="From account" value={pay.from} onChange={(e) => setPay({ ...pay, from: e.target.value })} />
          <input required placeholder="To account" value={pay.to} onChange={(e) => setPay({ ...pay, to: e.target.value })} />
          <input required type="number" min="0.01" step="0.01" placeholder="Amount" value={pay.amount} onChange={(e) => setPay({ ...pay, amount: e.target.value })} />
          <input placeholder="Description" value={pay.description} onChange={(e) => setPay({ ...pay, description: e.target.value })} />
          <button type="submit">Send</button>
        </form>
        <Message state={transfer} />
      </div>
    </section>
  );
}

function AuthorizePanel() {
  const [result, run] = useAction();
  const [decision, setDecision] = useState(null);
  const [form, setForm] = useState({
    account_id: "", amount: "", merchant: "", mcc: "5411", channel: "pos", device_id: "",
  });

  return (
    <section className="grid">
      <div className="card">
        <h2>Score a card authorization</h2>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const out = await run(
              () => api("/fraud/authorizations", {
                method: "POST",
                body: {
                  account_id: form.account_id,
                  amount_minor: Math.round(Number(form.amount) * 100),
                  currency: "USD",
                  merchant: form.merchant,
                  mcc: form.mcc,
                  channel: form.channel,
                  device_id: form.device_id || null,
                },
              }),
              (d) => `Decision: ${d.outcome}`,
            );
            setDecision(out);
          }}
        >
          <input required placeholder="Account id" value={form.account_id} onChange={(e) => setForm({ ...form, account_id: e.target.value })} />
          <input required type="number" min="0.01" step="0.01" placeholder="Amount" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
          <input required placeholder="Merchant" value={form.merchant} onChange={(e) => setForm({ ...form, merchant: e.target.value })} />
          <input required pattern="\d{4}" placeholder="MCC (4 digits)" value={form.mcc} onChange={(e) => setForm({ ...form, mcc: e.target.value })} />
          <select value={form.channel} onChange={(e) => setForm({ ...form, channel: e.target.value })}>
            <option value="pos">Card present (POS)</option>
            <option value="online">Card not present (online)</option>
            <option value="atm">ATM</option>
          </select>
          <input placeholder="Device id (optional)" value={form.device_id} onChange={(e) => setForm({ ...form, device_id: e.target.value })} />
          <button type="submit">Score</button>
        </form>
        <Message state={result} />
      </div>

      {decision && (
        <div className="card">
          <h2>Result</h2>
          <p className={`badge ${decision.outcome.toLowerCase()}`}>{decision.outcome}</p>
          <p>Risk score: {(decision.score * 100).toFixed(1)}%</p>
          <p className="muted">Model {decision.model_version}</p>
          {decision.reasons.length > 0 && (
            <ul>{decision.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          )}
        </div>
      )}
    </section>
  );
}

function CreditPanel() {
  const [result, run] = useAction();
  const [decision, setDecision] = useState(null);
  const [form, setForm] = useState({
    applicant_id: "", income: "", monthly_debt: "", utilization: "0.1",
    delinquencies: "0", history: "5", inquiries: "0", requested: "",
  });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  return (
    <section className="grid">
      <div className="card">
        <h2>Credit application</h2>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const out = await run(
              () => api("/credit/applications", {
                method: "POST",
                body: {
                  applicant_id: form.applicant_id,
                  annual_income_minor: Math.round(Number(form.income) * 100),
                  monthly_debt_minor: Math.round(Number(form.monthly_debt) * 100),
                  revolving_utilization: Number(form.utilization),
                  delinquencies_24m: Number(form.delinquencies),
                  credit_history_years: Number(form.history),
                  recent_inquiries_6m: Number(form.inquiries),
                  requested_minor: Math.round(Number(form.requested) * 100),
                },
              }),
              (d) => `Outcome: ${d.outcome}`,
            );
            setDecision(out);
          }}
        >
          <input required placeholder="Applicant reference" value={form.applicant_id} onChange={set("applicant_id")} />
          <input required type="number" min="1" placeholder="Annual income" value={form.income} onChange={set("income")} />
          <input required type="number" min="0" placeholder="Monthly debt payments" value={form.monthly_debt} onChange={set("monthly_debt")} />
          <input required type="number" min="0" max="1" step="0.01" placeholder="Card utilization (0-1)" value={form.utilization} onChange={set("utilization")} />
          <input required type="number" min="0" placeholder="Late payments, last 24 months" value={form.delinquencies} onChange={set("delinquencies")} />
          <input required type="number" min="0" step="0.5" placeholder="Credit history (years)" value={form.history} onChange={set("history")} />
          <input required type="number" min="0" placeholder="Credit inquiries, last 6 months" value={form.inquiries} onChange={set("inquiries")} />
          <input required type="number" min="1" placeholder="Requested amount" value={form.requested} onChange={set("requested")} />
          <button type="submit">Assess</button>
        </form>
        <Message state={result} />
      </div>

      {decision && (
        <div className="card">
          <h2>Decision</h2>
          <p className={`badge ${decision.outcome.toLowerCase()}`}>{decision.outcome}</p>
          <p>Estimated probability of default: {(decision.probability_of_default * 100).toFixed(2)}%</p>
          <p>Approved amount: {money(decision.approved_amount_minor)}</p>
          {decision.reasons.length > 0 && (
            <>
              <h3>Reason codes</h3>
              <ul>{decision.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            </>
          )}
          <p className="muted">Model {decision.model_version}</p>
        </div>
      )}
    </section>
  );
}

function DecisionsPanel() {
  const [kind, setKind] = useState("");
  const [rows, setRows] = useState([]);
  const [msg, run] = useAction();

  return (
    <section className="card">
      <h2>Decision audit log</h2>
      <div className="row">
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">All</option>
          <option value="fraud">Fraud</option>
          <option value="credit">Credit</option>
        </select>
        <button
          onClick={() =>
            run(
              async () => {
                const data = await api(`/decisions?limit=100${kind ? `&kind=${kind}` : ""}`);
                setRows(data);
                return data;
              },
              (data) => `${data.length} decisions loaded`,
            )
          }
        >
          Refresh
        </button>
      </div>
      <Message state={msg} />
      <table>
        <thead>
          <tr><th>When</th><th>Kind</th><th>Subject</th><th>Outcome</th><th>Score</th><th>Reasons</th><th>Model</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{new Date(r.created_at).toLocaleString()}</td>
              <td>{r.kind}</td>
              <td>{r.subject_id}</td>
              <td>{r.outcome}</td>
              <td>{(r.score * 100).toFixed(1)}%</td>
              <td>{r.reasons.join("; ") || "—"}</td>
              <td className="muted">{r.model_version}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
