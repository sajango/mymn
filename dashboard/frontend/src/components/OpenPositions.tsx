import { useQuery } from '@tanstack/react-query'
import { AlertCircle, TrendingUp, TrendingDown } from 'lucide-react'
import axios from 'axios'

interface Position {
  id: number
  ticket: number
  symbol: string
  action: string
  volume: number
  entry_price: number
  stop_loss: number
  take_profit: number | null
  open_time: string
  trailing_state: string
  confidence: number | null
  wave_position: string | null
}

export function OpenPositions() {
  const { data, isLoading, error } = useQuery<Position[]>({
    queryKey: ['positions'],
    queryFn: () => axios.get('/api/positions').then(res => res.data),
  })

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow p-4">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">Open Positions</h3>
        <div className="h-24 bg-gray-100 animate-pulse rounded" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow p-4">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">Open Positions</h3>
        <div className="flex items-center gap-2 text-red-500">
          <AlertCircle className="w-4 h-4" />
          Error loading positions
        </div>
      </div>
    )
  }

  if (!data || data.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-4">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">Open Positions</h3>
        <p className="text-gray-500 text-center py-4">No open positions</p>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <h3 className="text-lg font-semibold text-gray-800 mb-4">
        Open Positions ({data.length})
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left">
              <th className="py-2 text-gray-600">Ticket</th>
              <th className="py-2 text-gray-600">Symbol</th>
              <th className="py-2 text-gray-600">Type</th>
              <th className="py-2 text-gray-600">Volume</th>
              <th className="py-2 text-gray-600">Entry</th>
              <th className="py-2 text-gray-600">SL</th>
              <th className="py-2 text-gray-600">TP</th>
              <th className="py-2 text-gray-600">Trail</th>
              <th className="py-2 text-gray-600">Opened</th>
            </tr>
          </thead>
          <tbody>
            {data.map((pos) => (
              <tr key={pos.id} className="border-b last:border-0 hover:bg-gray-50">
                <td className="py-2 font-mono">{pos.ticket}</td>
                <td className="py-2">{pos.symbol}</td>
                <td className="py-2">
                  <span className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${
                    pos.action === 'BUY'
                      ? 'bg-green-100 text-green-700'
                      : 'bg-red-100 text-red-700'
                  }`}>
                    {pos.action === 'BUY' ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                    {pos.action}
                  </span>
                </td>
                <td className="py-2">{pos.volume}</td>
                <td className="py-2 font-mono">{pos.entry_price.toFixed(2)}</td>
                <td className="py-2 font-mono text-red-600">{pos.stop_loss.toFixed(2)}</td>
                <td className="py-2 font-mono text-green-600">
                  {pos.take_profit ? pos.take_profit.toFixed(2) : '-'}
                </td>
                <td className="py-2">
                  <span className={`px-2 py-1 rounded text-xs ${
                    pos.trailing_state === 'trailing'
                      ? 'bg-blue-100 text-blue-700'
                      : pos.trailing_state === 'activated'
                      ? 'bg-yellow-100 text-yellow-700'
                      : 'bg-gray-100 text-gray-600'
                  }`}>
                    {pos.trailing_state}
                  </span>
                </td>
                <td className="py-2 text-gray-500 text-xs">
                  {new Date(pos.open_time).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
