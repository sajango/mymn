import { useQuery } from '@tanstack/react-query'
import { RefreshCw, Activity } from 'lucide-react'
import axios from 'axios'
import { StatsCards } from './components/StatsCards'
import { EquityCurve } from './components/EquityCurve'
import { DailyPnLChart } from './components/DailyPnLChart'
import { TradesTable } from './components/TradesTable'
import { ConfidenceChart } from './components/ConfidenceChart'
import { TimeHeatmap } from './components/TimeHeatmap'
import { OpenPositions } from './components/OpenPositions'

const api = axios.create({
  baseURL: '/api',
})

function App() {
  const { data: stats, isLoading: statsLoading, refetch } = useQuery({
    queryKey: ['stats'],
    queryFn: () => api.get('/stats').then(res => res.data),
  })

  return (
    <div className="min-h-screen p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Activity className="w-8 h-8 text-blue-600" />
          <h1 className="text-2xl font-bold text-gray-800">
            MT5 Trading Dashboard
          </h1>
        </div>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Stats Cards */}
      <div className="mb-6">
        {statsLoading ? (
          <div className="h-24 bg-white rounded-lg animate-pulse" />
        ) : stats ? (
          <StatsCards stats={stats} />
        ) : null}
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <EquityCurve />
        <DailyPnLChart />
      </div>

      {/* Analysis Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <ConfidenceChart />
        <TimeHeatmap />
      </div>

      {/* Open Positions */}
      <div className="mb-6">
        <OpenPositions />
      </div>

      {/* Trades Table */}
      <div className="mb-6">
        <TradesTable />
      </div>

      {/* Footer */}
      <div className="text-center text-gray-500 text-sm">
        <p>Auto-refreshes every 30 seconds | Read-only dashboard</p>
      </div>
    </div>
  )
}

export default App
