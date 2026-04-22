import { Card, CardContent } from '@/components/ui/card'

interface KnowledgeGraphFeedbackCardsProps {
  graphSearchError: string | null
  graphError: string | null
  graphNotice: string | null
}

function ErrorCard({ message }: { message: string }) {
  return (
    <Card>
      <CardContent className="py-4 text-sm text-destructive">{message}</CardContent>
    </Card>
  )
}

export function KnowledgeGraphFeedbackCards({
  graphSearchError,
  graphError,
  graphNotice,
}: KnowledgeGraphFeedbackCardsProps) {
  return (
    <>
      {graphSearchError ? <ErrorCard message={graphSearchError} /> : null}
      {graphError ? <ErrorCard message={graphError} /> : null}
      {graphNotice ? (
        <Card>
          <CardContent className="py-4 text-sm text-muted-foreground">{graphNotice}</CardContent>
        </Card>
      ) : null}
    </>
  )
}
