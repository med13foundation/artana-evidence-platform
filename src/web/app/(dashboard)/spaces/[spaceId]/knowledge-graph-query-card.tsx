import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

interface KnowledgeGraphQueryCardProps {
  questionInput: string
  topKInput: string
  maxDepthInput: string
  forceAgent: boolean
  minDepth: number
  maxDepth: number
  minTopK: number
  maxTopK: number
  isLoading: boolean
  onQuestionInputChange: (value: string) => void
  onTopKInputChange: (value: string) => void
  onMaxDepthInputChange: (value: string) => void
  onForceAgentChange: (checked: boolean) => void
  onSearch: () => Promise<void>
  onLoadStarter: () => void
  onResetFilters: () => void
  autoFocusQuestion?: boolean
  variant?: 'default' | 'floating' | 'menu'
  orientation?: 'horizontal' | 'vertical'
  className?: string
}

export function KnowledgeGraphQueryCard({
  questionInput,
  topKInput,
  maxDepthInput,
  forceAgent,
  minDepth,
  maxDepth,
  minTopK,
  maxTopK,
  isLoading,
  onQuestionInputChange,
  onTopKInputChange,
  onMaxDepthInputChange,
  onForceAgentChange,
  onSearch,
  onLoadStarter,
  onResetFilters,
  autoFocusQuestion = false,
  variant = 'default',
  orientation = 'horizontal',
  className,
}: KnowledgeGraphQueryCardProps) {
  const isVertical = orientation === 'vertical'

  const form = (
    <form
      className={cn('space-y-4', variant === 'floating' && 'space-y-3')}
      onSubmit={(event) => {
        event.preventDefault()
        void onSearch()
      }}
    >
      <div className={cn(isVertical ? 'space-y-3' : 'grid gap-3 lg:grid-cols-4')}>
        <div className={cn('space-y-1', !isVertical && 'lg:col-span-2')}>
          <Label htmlFor="graph-query" className={cn(variant === 'floating' && 'text-xs')}>
            Graph Search Query
          </Label>
          <Input
            id="graph-query"
            value={questionInput}
            onChange={(event) => onQuestionInputChange(event.target.value)}
            placeholder="What evidence links MED13 to cardiac phenotypes?"
            autoFocus={autoFocusQuestion}
            className={cn(variant === 'floating' && 'h-9')}
          />
        </div>

        <div className={cn(isVertical ? 'grid grid-cols-2 gap-3' : 'contents')}>
          <div className="space-y-1">
            <Label htmlFor="graph-max-depth" className={cn(variant === 'floating' && 'text-xs')}>
              Max Depth
            </Label>
            <Input
              id="graph-max-depth"
              type="number"
              min={minDepth}
              max={maxDepth}
              value={maxDepthInput}
              onChange={(event) => onMaxDepthInputChange(event.target.value)}
              className={cn(variant === 'floating' && 'h-9')}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="graph-top-k" className={cn(variant === 'floating' && 'text-xs')}>
              Top K
            </Label>
            <Input
              id="graph-top-k"
              type="number"
              min={minTopK}
              max={maxTopK}
              value={topKInput}
              onChange={(event) => onTopKInputChange(event.target.value)}
              className={cn(variant === 'floating' && 'h-9')}
            />
          </div>
        </div>

        <div
          className={cn(
            'flex flex-wrap gap-2',
            variant === 'floating' && 'items-end',
            isVertical && 'flex-col [&>button]:w-full',
          )}
        >
          <Button type="submit" disabled={isLoading} className={cn(variant === 'floating' && 'h-9')}>
            {isLoading ? 'Running…' : 'Run Graph Search'}
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={isLoading}
            onClick={onLoadStarter}
            className={cn(variant === 'floating' && 'h-9')}
          >
            Load Starter Subgraph
          </Button>
          <Button
            type="button"
            variant="ghost"
            disabled={isLoading}
            onClick={onResetFilters}
            className={cn(variant === 'floating' && 'h-9')}
          >
            Reset Filters
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <Checkbox
          id="graph-force-agent"
          checked={forceAgent}
          onCheckedChange={(checked) => onForceAgentChange(checked === true)}
        />
        <Label htmlFor="graph-force-agent" className={cn(variant === 'floating' && 'text-xs')}>
          Force agent fallback
        </Label>
      </div>
    </form>
  )

  if (variant === 'floating') {
    return (
      <div
        className={cn(
          'rounded-2xl border border-border/70 bg-background/90 p-3 shadow-brand-sm backdrop-blur supports-[backdrop-filter]:bg-background/75 sm:p-4',
          className,
        )}
      >
        {form}
      </div>
    )
  }

  if (variant === 'menu') {
    return <div className={cn('p-3 sm:p-4', className)}>{form}</div>
  }

  return (
    <Card className={className}>
      <CardContent className="py-4">{form}</CardContent>
    </Card>
  )
}
