import { useQuery } from '@tanstack/react-query'
import axios from 'axios'

interface TimeAnalysis {
  by_hour: Array<{
    hour: number
    trades: number
    win_rate: number
    pnl: number
  }>
  by_day: Array<{
    day: string
    trades: number
    win_rate: number
    pnl: number
  }>
}

function getColorClass(winRate: number): string {
  if (winRate >= 70) return 'bg-green-500 text-white'
  if (winRate >= 55) return 'bg-green-300 text-gray-800'
  if (winRate >= 45) return 'bg-gray-200 text-gray-800'
  if (winRate >= 30) return 'bg-red-300 text-gray-800'
  return 'bg-red-500 text-white'
}

export function TimeHeatmap() {
  const { data, isLoading, error } = useQuery<TimeAnalysis>({
    queryKey: ['time-analysis'],
    queryFn: () => axios.get('/api/time-analysis').then(res => res.data),
  })

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow p-4 h-80">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">Performance by Time</h3>
        <div className="h-64 bg-gray-100 animate-pulse rounded" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="bg-white rounded-lg shadow p-4 h-80">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">Performance by Time</h3>
        <div className="h-64 flex items-center justify-center text-gray-400">
          No data available
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <h3 className="text-lg font-semibold text-gray-800 mb-4">Performance by Time</h3>

      {/* Day of Week */}
      <div className="mb-6">
        <h4 className="text-sm font-medium text-gray-600 mb-2">By Day of Week</h4>
        <div className="flex gap-2">
          {data.by_day.map((d) => (
            <div
              key={d.day}
              className={`flex-1 p-2 rounded text-center text-xs ${getColorClass(d.win_rate)}`}
              title={`${d.trades} trades, ${d.win_rate}% win rate, $${d.pnl} P&L`}
            >
              <div className="font-medium">{d.day}</div>
              <div>{d.win_rate}%</div>
              <div className="text-xs opacity-75">{d.trades} trades</div>
            </div>
          ))}
        </div>
      </div>

      {/* Hour of Day */}
      <div>
        <h4 className="text-sm font-medium text-gray-600 mb-2">By Hour (UTC)</h4>
        <div className="grid grid-cols-12 gap-1">
          {Array.from({ length: 24 }, (_, i) => {
            const hourData = data.by_hour.find(h => h.hour === i)
            return (
              <div
                key={i}
                className={`p-1 rounded text-center text-xs ${
                  hourData ? getColorClass(hourData.win_rate) : 'bg-gray-100 text-gray-400'
                }`}
                title={hourData
                  ? `${hourData.trades} trades, ${hourData.win_rate}% win, $${hourData.pnl}`
                  : 'No trades'
                }
              >
                {String(i).padStart(2, '0')}
              </div>
            )
          })}
        </div>
        <div className="flex justify-between text-xs text-gray-400 mt-1">
          <span>00:00</span>
          <span>12:00</span>
          <span>23:00</span>
        </div>
      </div>

      {/* Legend */}
      <div className="mt-4 flex items-center gap-4 text-xs text-gray-600">
        <span>Win Rate:</span>
        <div className="flex gap-1">
          <span className="px-2 py-1 bg-red-500 text-white rounded">&lt;30%</span>
          <span className="px-2 py-1 bg-red-300 rounded">30-45%</span>
          <span className="px-2 py-1 bg-gray-200 rounded">45-55%</span>
          <span className="px-2 py-1 bg-green-300 rounded">55-70%</span>
          <span className="px-2 py-1 bg-green-500 text-white rounded">&gt;70%</span>
        </div>
      </div>
    </div>
  )
}
