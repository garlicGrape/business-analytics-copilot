import { useEffect, useRef, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import './App.css'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'
const THREAD_ID = 'dashboard-session'

function RevenueByCategoryChart() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch(`${API_BASE}/stats/top-categories`)
      .then((res) => res.json())
      .then(setData)
      .catch((err) => setError(err.message))
  }, [])

  if (error) return <p className="error">Couldn't load chart: {error}</p>
  if (!data) return <p>Loading chart...</p>

  return (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={data} layout="vertical" margin={{ left: 24 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis type="number" />
        <YAxis type="category" dataKey="category" width={140} />
        <Tooltip formatter={(value) => `$${value.toLocaleString()}`} />
        <Bar dataKey="revenue" fill="#4f46e5" />
      </BarChart>
    </ResponsiveContainer>
  )
}

function Chat() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content:
        "Ask me about order/revenue data or what companies disclosed in their latest 10-K filings.",
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function sendMessage(e) {
    e.preventDefault()
    const text = input.trim()
    if (!text || loading) return

    setMessages((m) => [...m, { role: 'user', content: text }])
    setInput('')
    setLoading(true)

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thread_id: THREAD_ID, message: text }),
      })
      if (!res.ok) throw new Error(`server returned ${res.status}`)
      const data = await res.json()
      setMessages((m) => [...m, { role: 'assistant', content: data.response }])
    } catch (err) {
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: `Error reaching agent: ${err.message}` },
      ])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="chat">
      <div className="messages">
        {messages.map((m, i) => (
          <div key={i} className={`message ${m.role}`}>
            {m.content}
          </div>
        ))}
        {loading && <div className="message assistant">thinking...</div>}
        <div ref={bottomRef} />
      </div>
      <form onSubmit={sendMessage} className="composer">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g. What were total sales in São Paulo in 2017?"
        />
        <button type="submit" disabled={loading}>
          Send
        </button>
      </form>
    </div>
  )
}

function App() {
  return (
    <div className="dashboard">
      <header>
        <h1>Business Analytics Copilot</h1>
        <p>LangGraph agent over Olist e-commerce data + SEC 10-K filings, on Supabase.</p>
      </header>
      <main>
        <section className="panel">
          <h2>Revenue by category</h2>
          <RevenueByCategoryChart />
        </section>
        <section className="panel">
          <h2>Ask the copilot</h2>
          <Chat />
        </section>
      </main>
    </div>
  )
}

export default App
