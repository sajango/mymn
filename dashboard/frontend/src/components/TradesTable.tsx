import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, TrendingUp, TrendingDown } from 'lucide-react'
import axios from 'axios'

interface Trade {
  id: number
  ticket: number
  symbol: string
  action: string
  volume: number
  entry_price: number
  stop_loss: number
  close_price: number | null
  profit: number | null
  open_time: string
  close_time: string | null
  status: string
  confidence: number | null
  signal_action: string | null
}

interface TradesResponse {
  trades: Trade[]
  total: number
  limit: number
  offset: number
}

export function TradesTable() {
  const [page, setPage] = useState(0)
  const [status, setStatus] = useState<string>('')
  const limit = 10

  const { data, isLoading, error } = useQuery<TradesResponse>({
    queryKey: ['trades', page, status],
    queryFn: () => {
      const params = new URLSearchParams({
        limit: String(limit),
        offset: String(page * limit),
      })
      if (status) params.set('status', status)
      return axios.get(`/api/trades?${params}`).then(res => res.data)
    },
  })

  const totalPages = data ? Math.ceil(data.total / limit) : 0

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-800">Trade History</h3>
        <div className="flex gap-2">
          <select
            value={status}
            onChange={(e) => { setStatus(e.target.value); setPage(0) }}
            className="px-3 py-1 border rounded text-sm"
          >
            <option value="">All Status</option>
            <option value="open">Open</option>
            <option value="partial">Partial</option>
            <option value="closed">Closed</option>
          </select>
        </div>
      </div>

      {isLoading ? (
        <div className="h-64 bg-gray-100 animate-pulse rounded" />
      ) : error ? (
        <div className="h-64 flex items-center justify-center text-red-500">
          Error loading trades
        </div>
      ) : !data || data.trades.length === 0 ? (
        <div className="h-64 flex items-center justify-center text-gray-400">
          No trades found
        </div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="py-2 text-gray-600">Ticket</th>
                  <th className="py-2 text-gray-600">Type</th>
                  <th className="py-2 text-gray-600">Volume</th>
                  <th className="py-2 text-gray-600">Entry</th>
                  <th className="py-2 text-gray-600">Close</th>
                  <th className="py-2 text-gray-600">P&L</th>
                  <th className="py-2 text-gray-600">Confidence</th>
                  <th className="py-2 text-gray-600">Status</th>
                  <th className="py-2 text-gray-600">Opened</th>
                </tr>
              </thead>
              <tbody>
                {data.trades.map((trade) => (
                  <tr key={trade.id} className="border-b last:border-0 hover:bg-gray-50">
                    <td className="py-2 font-mono text-xs">{trade.ticket}</td>
                    <td className="py-2">
                      <span className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${
                        trade.action === 'BUY'
                          ? 'bg-green-100 text-green-700'
                          : 'bg-red-100 text-red-700'
                      }`}>
                        {trade.action === 'BUY' ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                        {trade.action}
                      </span>
                    </td>
                    <td className="py-2">{trade.volume}</td>
                    <td className="py-2 font-mono">{trade.entry_price.toFixed(2)}</td>
                    <td className="py-2 font-mono">
                      {trade.close_price ? trade.close_price.toFixed(2) : '-'}
                    </td>
                    <td className={`py-2 font-mono font-medium ${
                      trade.profit === null
                        ? 'text-gray-400'
                        : trade.profit >= 0
                        ? 'text-green-600'
                        : 'text-red-600'
                    }`}>
                      {trade.profit !== null ? `$${trade.profit.toFixed(2)}` : '-'}
                    </td>
                    <td className="py-2">
                      {trade.confidence !== null ? (
                        <span className={`px-2 py-1 rounded text-xs ${
                          trade.confidence >= 75
                            ? 'bg-green-100 text-green-700'
                            : trade.confidence >= 60
                            ? 'bg-yellow-100 text-yellow-700'
                            : 'bg-gray-100 text-gray-600'
                        }`}>
                          {trade.confidence}%
                        </span>
                      ) : '-'}
                    </td>
                    <td className="py-2">
                      <span className={`px-2 py-1 rounded text-xs ${
                        trade.status === 'closed'
                          ? 'bg-gray-100 text-gray-600'
                          : trade.status === 'open'
                          ? 'bg-blue-100 text-blue-700'
                          : 'bg-yellow-100 text-yellow-700'
                      }`}>
                        {trade.status}
                      </span>
                    </td>
                    <td className="py-2 text-gray-500 text-xs">
                      {new Date(trade.open_time).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between mt-4">
            <p className="text-sm text-gray-500">
              Showing {page * limit + 1} to {Math.min((page + 1) * limit, data.total)} of {data.total}
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={page === 0}
                className="p-2 rounded border disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="px-3 py-2 text-sm">
                Page {page + 1} of {totalPages}
              </span>
              <button
                onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="p-2 rounded border disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
