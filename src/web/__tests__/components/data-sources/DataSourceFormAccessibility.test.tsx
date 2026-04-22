import { render, screen } from '@testing-library/react'
import { useForm } from 'react-hook-form'
import type { ButtonHTMLAttributes } from 'react'

import { Form } from '@/components/ui/form'
import {
  AiManagedConfigFields,
  PubMedConfigFields,
} from '@/components/data-sources/DataSourceAiConfigFormFields'
import { DataSourceScheduleFields } from '@/components/data-sources/DataSourceScheduleFields'
import type { AiConfigFormValues } from '@/components/data-sources/DataSourceAiConfigDialog'
import type { ScheduleFormValues } from '@/components/data-sources/DataSourceScheduleDialog'

jest.mock('@/components/data-sources/AiModelSelector', () => ({
  AiModelSelector: ({
    value,
    onChange,
    ...props
  }: {
    value: string | null
    onChange: (value: string | null) => void
  } & ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button type="button" onClick={() => onChange(value)} {...props}>
      Model selector
    </button>
  ),
}))

function expectAllLabelsToReferenceExistingControls(container: HTMLElement) {
  const labels = Array.from(container.querySelectorAll('label[for]'))
  expect(labels.length).toBeGreaterThan(0)
  labels.forEach((label) => {
    const targetId = label.getAttribute('for')
    expect(targetId).toBeTruthy()
    expect(document.getElementById(targetId ?? '')).not.toBeNull()
  })
}

function AiFieldsHarness() {
  const form = useForm<AiConfigFormValues>({
    defaultValues: {
      use_research_space_context: true,
      agent_prompt: '',
      model_id: null,
      max_results: 5,
      open_access_only: true,
    },
  })

  return (
    <Form {...form}>
      <form>
        <AiManagedConfigFields form={form} isPubMedSource={true} />
        <PubMedConfigFields form={form} />
      </form>
    </Form>
  )
}

function ScheduleFieldsHarness() {
  const form = useForm<ScheduleFormValues>({
    defaultValues: {
      enabled: true,
      frequency: 'daily',
      startTime: '2026-03-05T09:00',
      timezone: 'UTC',
      cronExpression: '',
    },
  })

  return (
    <Form {...form}>
      <form>
        <DataSourceScheduleFields control={form.control} setValue={form.setValue} />
      </form>
    </Form>
  )
}

describe('data source form accessibility wiring', () => {
  it('keeps AI configuration labels bound to real controls and exposes stable names', () => {
    const { container } = render(<AiFieldsHarness />)

    expectAllLabelsToReferenceExistingControls(container)
    expect(
      screen.getByRole('switch', { name: /use research space context/i }),
    ).toHaveAttribute('name', 'use_research_space_context')
    expect(
      screen.getByRole('spinbutton', { name: /per-run paper cap/i }),
    ).toHaveAttribute('name', 'max_results')
  })

  it('avoids orphaned labels in schedule fields and assigns names to freeform inputs', () => {
    const { container } = render(<ScheduleFieldsHarness />)

    expectAllLabelsToReferenceExistingControls(container)
    expect(screen.getByLabelText('Schedule time')).toHaveAttribute('name', 'schedule_time')
  })
})
