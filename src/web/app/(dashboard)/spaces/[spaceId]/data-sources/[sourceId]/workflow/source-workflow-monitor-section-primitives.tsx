import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export function ChecklistItem({ label, isReady }: { label: string; isReady: boolean }) {
  return (
    <div className="flex items-center justify-between rounded border px-3 py-2 text-xs">
      <span>{label}</span>
      <Badge variant={isReady ? 'secondary' : 'outline'}>{isReady ? 'Ready' : 'Pending'}</Badge>
    </div>
  )
}

export function CountCard({ title, value }: { title: string; value: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-semibold">{value}</div>
      </CardContent>
    </Card>
  )
}
