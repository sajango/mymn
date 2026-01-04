import { useQuery } from '@tanstack/react-query'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Cell,
} from 'recharts'
import axios from 'axios'

interface DailyPnL {
  date: string
  pnl: number
  trades: number
}

export function DailyPnLChart() {
  const { data, isLoading, error } = useQuery<DailyPnL[]>({
    queryKey: ['daily-pnl'],
    queryFn: () => axios.get('/api/daily-pnl?days=30').then(res => res.data),
  })

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow p-4 h-80">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">Daily P&L (30 Days)</h3>
        <div className="h-64 bg-gray-100 animate-pulse rounded" />
      </div>
    )
  }

  if (error || !data || data.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-4 h-80">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">Daily P&L (30 Days)</h3>
        <div className="h-64 flex items-center justify-center text-gray-400">
          No data available
        </div>
      </div>
    )
  }

  // Format dates
  const formattedData = data.map(d => ({
    ...d,
    day: new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
  }))

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <h3 className="text-lg font-semibold text-gray-800 mb-4">Daily P&L (30 Days)</h3>
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={formattedData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis
            dataKey="day"
            tick={{ fontSize: 10 }}
            stroke="#9ca3af"
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontSize: 12 }}
            stroke="#9ca3af"
            tickFormatter={(val) => `$${val}`}
          />
          <Tooltip
            formatter={(value: number, name: string) => {
              if (name === 'pnl') return [`$${value.toFixed(2)}`, 'P&L']
              return [value, 'Trades']
            }}
            contentStyle={{ borderRadius: '8px' }}
          />
          <ReferenceLine y={0} stroke="#9ca3af" strokeDasharray="3 3" />
          <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
            {formattedData.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={entry.pnl >= 0 ? '#10b981' : '#ef4444'}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
