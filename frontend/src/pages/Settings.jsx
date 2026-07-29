import { useEffect, useState } from 'react'
import { getSettings, updateSettings } from '../api'
import { money } from '../format'

// Both targets are the same shape of thing — a number you set and then get
// measured against — so they are the same form, told apart by their copy.
function TargetForm({ label, hint, field, value, onSaved }) {
  const [amount, setAmount] = useState('')
  const [saved, setSaved] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => { setAmount(String(value)) }, [value])

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setSaved(null)
    const next = parseFloat(amount)
    try {
      // Only this field goes: the other target is left exactly as it was.
      await updateSettings({ [field]: next })
      setSaved(next)
      onSaved()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="panel">
      <h2 className="panel-title">{label}</h2>
      <form onSubmit={submit} className="controls">
        <label className="field">
          <span className="field-label">Amount</span>
          <input
            type="number" step="0.01" min="0" required size="10"
            value={amount}
            onChange={(e) => { setAmount(e.target.value); setSaved(null) }}
          />
        </label>
        <button type="submit" className="btn">Save</button>
      </form>

      {saved !== null && <p className="confirm">{hint(saved)}</p>}
      {error && <p className="notice">{error}</p>}
    </div>
  )
}

export default function Settings() {
  const [settings, setSettings] = useState(null)
  const [error, setError] = useState('')

  const load = () => getSettings().then(setSettings).catch((err) => setError(err.message))

  useEffect(() => { load() }, [])

  if (error && !settings) return <p className="notice">{error}</p>
  if (!settings) return <p className="empty">Loading…</p>

  return (
    <div>
      <TargetForm
        label="Monthly spending budget"
        field="monthly_budget"
        value={settings.monthly_budget}
        onSaved={load}
        hint={(n) =>
          n > 0
            ? `Budget set to ${money(n)} a month. Overview now tracks your pace against it.`
            : 'Budget cleared. Overview will show your pace without a target.'
        }
      />

      <TargetForm
        label="Monthly savings target"
        field="savings_target"
        value={settings.savings_target}
        onSaved={load}
        hint={(n) =>
          n > 0
            ? `Target set to ${money(n)} a month. Savings will tell you how close you are.`
            : 'Target cleared. Savings will show what you kept without judging it.'
        }
      />

      <div className="panel">
        <h2 className="panel-title">Where your data lives</h2>
        <p className="confirm" style={{ marginTop: 0 }}>
          The ledger is a SQLite file on this machine and nothing is uploaded from it.
        </p>
        <p className="confirm">
          The written analysis on Overview is the one exception, and only if you have set
          a Gemini key: it sends monthly totals per category, your budget and your goal
          names. The notes you write on individual entries are never included.
        </p>
      </div>
    </div>
  )
}
