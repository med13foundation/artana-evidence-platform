"use client"

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { RegisterForm } from '@/components/auth/RegisterForm'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { AlertCircle, CheckCircle } from 'lucide-react'
import { AuthShell } from '@/components/auth/AuthShell'
import { CREATE_ACCOUNT_TITLE } from '@/lib/branding'
import type { RegisterRequest } from '@/types/auth'
import { registerUser } from '@/app/actions/auth'

export default function RegisterPage() {
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const router = useRouter()

  const handleRegister = async (data: RegisterRequest) => {
    setIsLoading(true)
    setError(null)
    setSuccess(null)

    try {
      const result = await registerUser(data)
      if (!result.success) {
        throw new Error(result.error)
      }

      setSuccess(result.message)

      // Redirect to login after a delay
      setTimeout(() => {
        router.push('/auth/login')
      }, 3000)
    } catch (error) {
      setError(error instanceof Error ? error.message : 'An unexpected error occurred')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <AuthShell
      title={CREATE_ACCOUNT_TITLE}
      description="Request access to the administrative interface."
      footer={
        <div className="text-center text-sm text-muted-foreground">
          Already verified?{" "}
          <Link href="/auth/login" className="text-primary hover:underline">
            Sign in
          </Link>
        </div>
      }
    >
      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertCircle className="size-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {success && (
        <Alert variant="success" className="mb-4">
          <CheckCircle className="size-4" />
          <AlertDescription>{success}</AlertDescription>
        </Alert>
      )}

      <RegisterForm onSubmit={handleRegister} isLoading={isLoading} />
    </AuthShell>
  )
}
