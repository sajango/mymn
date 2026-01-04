import { useQuery } from '@tanstack/react-query'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import axios from 'axios'

interface EquityPoint {
  time: string
  profit: number
  equity: number
}

export function EquityCurve() {
  const { data, isLoading, error } = useQuery<EquityPoint[]>({
    queryKey: ['equity'],
    queryFn: () => axios.get('/api/equity').then(res => res.data),
  })

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow p-4 h-80">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">Equity Curve</h3>
        <div className="h-64 bg-gray-100 animate-pulse rounded" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="bg-white rounded-lg shadow p-4 h-80">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">Equity Curve</h3>
        <div className="h-64 flex items-center justify-center text-gray-400">
          No data available
        </div>
      </div>
    )
  }

  // Format date for display
  const formattedData = data.map(d => ({
    ...d,
    date: new Date(d.time).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
  }))

  const minEquity = Math.min(0, ...data.map(d => d.equity))
  const maxEquity = Math.max(0, ...data.map(d => d.equity))

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <h3 className="text-lg font-semibold text-gray-800 mb-4">Equity Curve</h3>
      <ResponsiveContainer width="100%" height={250}>
        <LineChart data={formattedData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 12 }}
            stroke="#9ca3af"
          />
          <YAxis
            tick={{ fontSize: 12 }}
            stroke="#9ca3af"
            domain={[minEquity * 1.1, maxEquity * 1.1]}
            tickFormatter={(val) => `$${val}`}
          />
          <Tooltip
            formatter={(value: number) => [`$${value.toFixed(2)}`, 'Equity']}
            labelFormatter={(label) => `Date: ${label}`}
            contentStyle={{ borderRadius: '8px' }}
          />
          <ReferenceLine y={0} stroke="#9ca3af" strokeDasharray="3 3" />
          <Line
            type="monotone"
            dataKey="equity"
            stroke="#10b981"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
