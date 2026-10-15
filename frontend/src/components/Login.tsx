import React, { useState } from 'react'
import { api, Me } from '../api'

const s = {
  wrap: { minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 },
  card: {
    width: '100%', maxWidth: 360, background: 'var(--surface)', border: '1px solid var(--border)',
    borderRadius: 12, padding: 28, display: 'flex', flexDirection: 'column', gap: 14,
  },
  title: { fontWeight: 800, fontSize: 18, letterSpacing: '-0.5px' },
  label: { fontSize: 12, color: 'var(--muted)', fontWeight: 600 },
  input: {
    width: '100%', padding: '10px 12px', borderRadius: 8, marginTop: 6,
    background: 'var(--surface2)', border: '1px solid var(--border)', color: 'var(--text)', fontSize: 14, outline: 'none',
  },
  btn: { padding: '10px 16px', borderRadius: 8, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 14 },
} satisfies Record<string, React.CSSProperties>

export default function Login({ onLogin }: { onLogin: (me: Me) => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.login(username, password)
      onLogin(await api.me())
    } catch {
      setError('Invalid username or password')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={s.wrap}>
      <form style={s.card} onSubmit={submit}>
        <div style={s.title}>Company <span style={{ color: 'var(--accent)' }}>Knowledge Graph</span></div>
        <label style={s.label}>
          Username
          <input style={s.input} value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" autoFocus />
        </label>
        <label style={s.label}>
          Password
          <input style={s.input} type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" />
        </label>
        {error && <div style={{ color: 'var(--danger)', fontSize: 13 }}>{error}</div>}
        <button style={s.btn} type="submit" disabled={busy || !username || !password}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
