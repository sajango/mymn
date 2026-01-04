import { TrendingUp, TrendingDown, Target, Activity, Award, BarChart3 } from 'lucide-react'

interface Stats {
  total_trades: number
  wins: number
  losses: number
  win_rate: number
  total_pnl: number
  avg_profit: number
  max_profit: number
  max_loss: number
  profit_factor: number
}

interface CardProps {
  title: string
  value: string | number
  icon: React.ReactNode
  color?: 'green' | 'red' | 'blue' | 'gray'
  subtitle?: string
}

function Card({ title, value, icon, color = 'gray', subtitle }: CardProps) {
  const colorClasses = {
    green: 'text-green-600 bg-green-50',
    red: 'text-red-600 bg-red-50',
    blue: 'text-blue-600 bg-blue-50',
    gray: 'text-gray-600 bg-gray-50',
  }

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-500">{title}</p>
          <p className={`text-2xl font-bold ${color === 'green' ? 'text-green-600' : color === 'red' ? 'text-red-600' : 'text-gray-900'}`}>
            {value}
          </p>
          {subtitle && <p className="text-xs text-gray-400 mt-1">{subtitle}</p>}
        </div>
        <div className={`p-3 rounded-lg ${colorClasses[color]}`}>
          {icon}
        </div>
      </div>
    </div>
  )
}

export function StatsCards({ stats }: { stats: Stats }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
      <Card
        title="Total P&L"
        value={`$${stats.total_pnl.toLocaleString()}`}
        icon={stats.total_pnl >= 0 ? <TrendingUp className="w-5 h-5" /> : <TrendingDown className="w-5 h-5" />}
        color={stats.total_pnl >= 0 ? 'green' : 'red'}
      />
      <Card
        title="Win Rate"
        value={`${stats.win_rate}%`}
        icon={<Target className="w-5 h-5" />}
        color={stats.win_rate >= 50 ? 'green' : 'red'}
      />
      <Card
        title="Total Trades"
        value={stats.total_trades}
        icon={<Activity className="w-5 h-5" />}
        color="blue"
        subtitle={`${stats.wins}W / ${stats.losses}L`}
      />
      <Card
        title="Avg Profit"
        value={`$${stats.avg_profit.toLocaleString()}`}
        icon={<BarChart3 className="w-5 h-5" />}
        color={stats.avg_profit >= 0 ? 'green' : 'red'}
      />
      <Card
        title="Best Trade"
        value={`$${stats.max_profit.toLocaleString()}`}
        icon={<Award className="w-5 h-5" />}
        color="green"
      />
      <Card
        title="Profit Factor"
        value={stats.profit_factor.toFixed(2)}
        icon={<TrendingUp className="w-5 h-5" />}
        color={stats.profit_factor >= 1 ? 'green' : 'red'}
      />
    </div>
  )
}
