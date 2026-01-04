import { useQuery } from '@tanstack/react-query'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import axios from 'axios'

interface ConfidenceBand {
  band: string
  total: number
  wins: number
  win_rate: number
  avg_profit: number
  total_profit: number
}

export function ConfidenceChart() {
  const { data, isLoading, error } = useQuery<ConfidenceBand[]>({
    queryKey: ['confidence-analysis'],
    queryFn: () => axios.get('/api/confidence-analysis').then(res => res.data),
  })

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow p-4 h-80">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">Confidence vs Performance</h3>
        <div className="h-64 bg-gray-100 animate-pulse rounded" />
      </div>
    )
  }

  if (error || !data || data.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-4 h-80">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">Confidence vs Performance</h3>
        <div className="h-64 flex items-center justify-center text-gray-400">
          No data available
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <h3 className="text-lg font-semibold text-gray-800 mb-4">Confidence vs Performance</h3>
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis
            dataKey="band"
            tick={{ fontSize: 11 }}
            stroke="#9ca3af"
          />
          <YAxis
            yAxisId="left"
            tick={{ fontSize: 12 }}
            stroke="#9ca3af"
            tickFormatter={(val) => `${val}%`}
          />
          <YAxis
            yAxisId="right"
            orientation="right"
            tick={{ fontSize: 12 }}
            stroke="#9ca3af"
            tickFormatter={(val) => `$${val}`}
          />
          <Tooltip
            formatter={(value: number, name: string) => {
              if (name === 'win_rate') return [`${value}%`, 'Win Rate']
              if (name === 'avg_profit') return [`$${value.toFixed(2)}`, 'Avg Profit']
              return [value, name]
            }}
            contentStyle={{ borderRadius: '8px' }}
          />
          <Legend />
          <Bar
            yAxisId="left"
            dataKey="win_rate"
            fill="#3b82f6"
            name="Win Rate %"
            radius={[4, 4, 0, 0]}
          />
          <Bar
            yAxisId="right"
            dataKey="avg_profit"
            fill="#10b981"
            name="Avg Profit $"
            radius={[4, 4, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>

      {/* Summary Table */}
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b">
              <th className="text-left py-2 text-gray-600">Confidence</th>
              <th className="text-right py-2 text-gray-600">Trades</th>
              <th className="text-right py-2 text-gray-600">Win Rate</th>
              <th className="text-right py-2 text-gray-600">Total P&L</th>
            </tr>
          </thead>
          <tbody>
            {data.map((row) => (
              <tr key={row.band} className="border-b last:border-0">
                <td className="py-2">{row.band}</td>
                <td className="text-right">{row.total}</td>
                <td className="text-right">{row.win_rate}%</td>
                <td className={`text-right ${row.total_profit >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  ${row.total_profit.toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
