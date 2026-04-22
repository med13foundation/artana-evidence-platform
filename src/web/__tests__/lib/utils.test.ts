import { cn } from '@/lib/utils'

describe('cn utility function', () => {
  it('combines class names correctly', () => {
    expect(cn('class1', 'class2')).toBe('class1 class2')
  })

  it('handles conditional classes', () => {
    const isActive = true
    const isDisabled = false

    expect(cn(
      'base-class',
      isActive && 'active-class',
      isDisabled && 'disabled-class'
    )).toBe('base-class active-class')
  })

  it('merges conflicting Tailwind classes correctly', () => {
    expect(cn('text-red-500', 'text-blue-500')).toBe('text-blue-500')
  })

  it('handles undefined and null values', () => {
    expect(cn('class1', undefined, null, 'class2')).toBe('class1 class2')
  })

  it('handles empty strings', () => {
    expect(cn('class1', '', 'class2')).toBe('class1 class2')
  })

  it('handles falsy values', () => {
    expect(cn('class1', false && 'conditional', 'class2')).toBe('class1 class2')
  })

  it('handles array of classes', () => {
    expect(cn(['class1', 'class2'], 'class3')).toBe('class1 class2 class3')
  })

  it('handles nested arrays', () => {
    expect(cn(['class1', ['class2', 'class3']], 'class4')).toBe('class1 class2 class3 class4')
  })

  it('returns empty string for no arguments', () => {
    expect(cn()).toBe('')
  })

  it('handles complex Tailwind merging', () => {
    expect(cn(
      'px-2 py-1',
      'px-4',
      'bg-red-500 hover:bg-red-600',
      'bg-blue-500 hover:bg-blue-600'
    )).toBe('py-1 px-4 bg-blue-500 hover:bg-blue-600')
  })

  it('preserves important modifiers', () => {
    expect(cn('!text-red-500', 'text-blue-500')).toBe('!text-red-500 text-blue-500')
  })

  it('handles responsive variants', () => {
    expect(cn('sm:text-sm', 'md:text-base')).toBe('sm:text-sm md:text-base')
  })
})
