"use client"

import { AlertCircle, AlertTriangle, Info } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { ValidationIssueDTO } from '@/types/generated'

interface ValidationFeedbackProps {
  issues: ValidationIssueDTO[]
}

export function ValidationFeedback({ issues }: ValidationFeedbackProps) {
  if (!issues || issues.length === 0) return null

  return (
    <div className="space-y-2">
      {issues.map((issue, index) => {
        let Icon = AlertCircle
        let variant: "default" | "destructive" = "default"

        if (issue.severity === 'error') {
          variant = "destructive"
          Icon = AlertCircle
        } else if (issue.severity === 'warning') {
          // Alert component doesn't have warning variant by default, using default with custom styling could be an option
          // For now, mapping to default
          Icon = AlertTriangle
        } else {
          Icon = Info
        }

        return (
          <Alert key={index} variant={variant}>
            <Icon className="size-4" />
            <AlertTitle className="capitalize">{issue.severity || 'Error'}</AlertTitle>
            <AlertDescription>
              {issue.message}
              {issue.field && (
                <span className="ml-1 rounded bg-muted px-1 font-mono text-xs">
                  field: {issue.field}
                </span>
              )}
            </AlertDescription>
          </Alert>
        )
      })}
    </div>
  )
}
