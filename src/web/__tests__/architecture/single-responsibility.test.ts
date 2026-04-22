/**
 * Single Responsibility Principle Validation Tests
 *
 * Validates that frontend components follow SRP:
 * 1. Component size (lines of code)
 * 2. Number of responsibilities (hooks, effects, handlers)
 * 3. Prop complexity (number of props)
 * 4. Import count (dependencies)
 *
 * Per docs/frontend/EngineeringArchitectureNext.md:
 * - Components should be "dumb renderers"
 * - Components should receive data as props
 * - Business logic should stay in Python Domain Services
 */

import { describe, it, expect } from '@jest/globals'
import * as fs from 'fs'
import * as path from 'path'

// SRP thresholds for frontend components
const MAX_COMPONENT_LINES = 300
const MAX_COMPONENT_PROPS = 10
const MAX_COMPONENT_IMPORTS = 15
const MAX_HOOKS_PER_COMPONENT = 8
const MAX_HANDLERS_PER_COMPONENT = 10
const WARNING_COMPONENT_LINES = 200

const WEB_ROOT = path.join(__dirname, '../..')
const KNOWN_SRP_EXCEPTIONS = new Set<string>([
  'components/data-discovery/ParameterBar.tsx',
  'components/data-discovery/ResultsView.tsx',
  'components/data-sources/DataSourcesList.tsx',
  'components/data-sources/DataSourceConfigurationDialog.tsx',
  'components/data-sources/DataSourceScheduleFields.tsx',
  'components/navigation/RouteProgressBar.tsx',
  'components/research-spaces/ResearchSpaceDetail.tsx',
  'components/system-settings/DataSourceAvailabilitySection.tsx',
  'components/system-settings/StorageConfigurationManager.tsx',
  'components/templates/ValidationRulesDialog.tsx',
  'components/ui/sidebar.tsx',
  'app/(dashboard)/admin/data-sources/templates/[templateId]/template-detail-client.tsx',
  'app/(dashboard)/admin/data-sources/templates/templates-client.tsx',
  'app/(dashboard)/spaces/[spaceId]/knowledge-graph-client.tsx',
  'app/(dashboard)/spaces/[spaceId]/knowledge-graph-query-card.tsx',
  'app/(dashboard)/spaces/[spaceId]/knowledge-graph-visualization.tsx',
  'app/(dashboard)/spaces/[spaceId]/page.tsx',
  'app/(dashboard)/spaces/[spaceId]/space-curation-client.tsx',
  'app/(dashboard)/spaces/[spaceId]/space-settings-client.tsx',
  'app/(dashboard)/spaces/[spaceId]/use-knowledge-graph-controller.ts',
  'app/(dashboard)/system-settings/system-settings-client.tsx',
  'app/actions/kernel-ingest.ts',
])

const relativeToWebRoot = (filePath: string): string =>
  path.relative(WEB_ROOT, filePath)

const filterAllowed = (items: ComponentMetrics[]): ComponentMetrics[] =>
  items.filter((item) => !KNOWN_SRP_EXCEPTIONS.has(relativeToWebRoot(item.filePath)))

interface ComponentMetrics {
  filePath: string
  lines: number
  props: number
  imports: number
  hooks: number
  handlers: number
  violations: string[]
  warnings: string[]
}

/**
 * Analyze a component file for SRP violations.
 */
function analyzeComponent(filePath: string): ComponentMetrics {
  const content = fs.readFileSync(filePath, 'utf-8')
  const lines = content.split('\n')

  const metrics: ComponentMetrics = {
    filePath,
    lines: lines.length,
    props: 0,
    imports: 0,
    hooks: 0,
    handlers: 0,
    violations: [],
    warnings: [],
  }

  // Count imports
  const importMatches = content.match(/^import\s+.*from\s+['"]/gm)
  metrics.imports = importMatches ? importMatches.length : 0

  // Count hooks (useState, useEffect, etc.)
  const hookPattern =
    /\b(useState|useEffect|useCallback|useMemo|useReducer|useContext|useRef|useQuery|useMutation)\s*\(/g
  const hookMatches = content.match(hookPattern)
  metrics.hooks = hookMatches ? hookMatches.length : 0

  // Count handlers (onClick, onChange, handle*, etc.)
  const handlerPattern = /\b(on\w+|handle\w+)\s*[:=]/g
  const handlerMatches = content.match(handlerPattern)
  metrics.handlers = handlerMatches ? handlerMatches.length : 0

  // Extract props from interface/type definition
  const propsInterfaceMatch = content.match(
    /interface\s+\w+Props\s*\{([\s\S]+?)\}/
  )
  const propsTypeMatch = content.match(/type\s+\w+Props\s*=\s*\{([\s\S]+?)\}/)
  const propsMatch = propsInterfaceMatch || propsTypeMatch

  if (propsMatch) {
    const propsContent = propsMatch[1]
    // Count prop definitions (handle optional props with ?)
    const propMatches = propsContent.match(/^\s*\w+[?:]?\s*[:=]/gm)
    metrics.props = propMatches ? propMatches.length : 0
  }

  // Check violations (errors)
  if (metrics.lines > MAX_COMPONENT_LINES) {
    metrics.violations.push(
      `Component exceeds size limit: ${metrics.lines} > ${MAX_COMPONENT_LINES} lines`
    )
  }
  if (metrics.props > MAX_COMPONENT_PROPS) {
    metrics.violations.push(
      `Component has too many props: ${metrics.props} > ${MAX_COMPONENT_PROPS}`
    )
  }
  if (metrics.imports > MAX_COMPONENT_IMPORTS) {
    metrics.violations.push(
      `Component has too many dependencies: ${metrics.imports} > ${MAX_COMPONENT_IMPORTS} imports`
    )
  }
  if (metrics.hooks > MAX_HOOKS_PER_COMPONENT) {
    metrics.violations.push(
      `Component uses too many hooks: ${metrics.hooks} > ${MAX_HOOKS_PER_COMPONENT}`
    )
  }
  if (metrics.handlers > MAX_HANDLERS_PER_COMPONENT) {
    metrics.violations.push(
      `Component has too many handlers: ${metrics.handlers} > ${MAX_HANDLERS_PER_COMPONENT}`
    )
  }

  // Check warnings
  if (
    metrics.lines > WARNING_COMPONENT_LINES &&
    metrics.lines <= MAX_COMPONENT_LINES
  ) {
    metrics.warnings.push(
      `Component is large: ${metrics.lines} lines (approaching limit)`
    )
  }

  return metrics
}

/**
 * Recursively find all component files in a directory.
 */
function findComponentFiles(dir: string): string[] {
  const files: string[] = []

  if (!fs.existsSync(dir)) {
    return files
  }

  const entries = fs.readdirSync(dir, { withFileTypes: true })

  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name)

    if (
      entry.isDirectory() &&
      !entry.name.startsWith('.') &&
      entry.name !== 'node_modules' &&
      entry.name !== '__tests__' &&
      entry.name !== '__mocks__'
    ) {
      files.push(...findComponentFiles(fullPath))
    } else if (
      entry.isFile() &&
      (entry.name.endsWith('.tsx') || entry.name.endsWith('.ts'))
    ) {
      // Skip test files, generated files, and type definition files
      if (
        !entry.name.includes('.test.') &&
        !entry.name.includes('.spec.') &&
        !entry.name.includes('.generated.') &&
        !entry.name.includes('.d.ts') &&
        !entry.name.includes('.stories.')
      ) {
        files.push(fullPath)
      }
    }
  }

  return files
}

describe('Single Responsibility Principle - Frontend Components', () => {
  const componentsDir = path.join(__dirname, '../../components')
  const appDir = path.join(__dirname, '../../app')

  // Find all component files
  const componentFiles = [
    ...findComponentFiles(componentsDir),
    ...findComponentFiles(appDir),
  ].filter((file) => {
    // Filter out non-component files (utilities, types, etc.)
    const content = fs.readFileSync(file, 'utf-8')
    // Include files that export React components or have JSX
    return (
      content.includes('export') &&
      (content.includes('function') ||
        content.includes('const') ||
        content.includes('class') ||
        content.includes('return') ||
        content.includes('JSX') ||
        content.includes('<'))
    )
  })

  it('should validate all components meet SRP thresholds', () => {
    const violations: ComponentMetrics[] = []

    for (const file of componentFiles) {
      const metrics = analyzeComponent(file)
      if (metrics.violations.length > 0) {
        violations.push(metrics)
      }
    }

    const actionableViolations = filterAllowed(violations)

    if (actionableViolations.length > 0) {
      const report = actionableViolations
        .map((v) => {
          const relativePath = relativeToWebRoot(v.filePath)
          return `\n${relativePath}:\n  ${v.violations.join('\n  ')}\n  Metrics: ${v.lines} lines, ${v.props} props, ${v.imports} imports, ${v.hooks} hooks, ${v.handlers} handlers`
        })
        .join('\n')

      throw new Error(
        `Found ${actionableViolations.length} components violating SRP:\n${report}\n\n` +
          'Consider splitting large components into smaller, focused components. ' +
          'Per docs/frontend/EngineeringArchitectureNext.md, components should be "dumb renderers".'
      )
    }

    expect(actionableViolations).toHaveLength(0)
  })

  it('should enforce component size limits', () => {
    const oversized: ComponentMetrics[] = []

    for (const file of componentFiles) {
      const metrics = analyzeComponent(file)
      if (metrics.lines > MAX_COMPONENT_LINES) {
        oversized.push(metrics)
      }
    }

    const actionableOversized = filterAllowed(oversized)

    if (actionableOversized.length > 0) {
      const report = actionableOversized
        .map((m) => {
          const relativePath = relativeToWebRoot(m.filePath)
          return `${relativePath}: ${m.lines} lines`
        })
        .join('\n')

      throw new Error(
        `Found ${actionableOversized.length} components exceeding size limit:\n${report}\n\n` +
          'Large components may violate Single Responsibility Principle. ' +
          'Split into smaller components that each handle a single responsibility.'
      )
    }

    expect(actionableOversized).toHaveLength(0)
  })

  it('should enforce prop complexity limits', () => {
    const complexProps: ComponentMetrics[] = []

    for (const file of componentFiles) {
      const metrics = analyzeComponent(file)
      if (metrics.props > MAX_COMPONENT_PROPS) {
        complexProps.push(metrics)
      }
    }

    const actionableComplexProps = filterAllowed(complexProps)

    if (actionableComplexProps.length > 0) {
      const report = actionableComplexProps
        .map((m) => {
          const relativePath = relativeToWebRoot(m.filePath)
          return `${relativePath}: ${m.props} props`
        })
        .join('\n')

      throw new Error(
        `Found ${actionableComplexProps.length} components with too many props:\n${report}\n\n` +
          'Components with many props may be doing too much. ' +
          'Consider using composition, context, or splitting into smaller components.'
      )
    }

    expect(actionableComplexProps).toHaveLength(0)
  })

  it('should enforce hook usage limits', () => {
    const excessiveHooks: ComponentMetrics[] = []

    for (const file of componentFiles) {
      const metrics = analyzeComponent(file)
      if (metrics.hooks > MAX_HOOKS_PER_COMPONENT) {
        excessiveHooks.push(metrics)
      }
    }

    const actionableHooks = filterAllowed(excessiveHooks)

    if (actionableHooks.length > 0) {
      const report = actionableHooks
        .map((m) => {
          const relativePath = relativeToWebRoot(m.filePath)
          return `${relativePath}: ${m.hooks} hooks`
        })
        .join('\n')

      throw new Error(
        `Found ${actionableHooks.length} components using too many hooks:\n${report}\n\n` +
          'Components with many hooks may have multiple responsibilities. ' +
          'Consider extracting logic into custom hooks or splitting the component.'
      )
    }

    expect(actionableHooks).toHaveLength(0)
  })

  it('should enforce handler count limits', () => {
    const excessiveHandlers: ComponentMetrics[] = []

    for (const file of componentFiles) {
      const metrics = analyzeComponent(file)
      if (metrics.handlers > MAX_HANDLERS_PER_COMPONENT) {
        excessiveHandlers.push(metrics)
      }
    }

    const actionableHandlers = filterAllowed(excessiveHandlers)

    if (actionableHandlers.length > 0) {
      const report = actionableHandlers
        .map((m) => {
          const relativePath = relativeToWebRoot(m.filePath)
          return `${relativePath}: ${m.handlers} handlers`
        })
        .join('\n')

      throw new Error(
        `Found ${actionableHandlers.length} components with too many handlers:\n${report}\n\n` +
          'Components with many handlers may be handling too many responsibilities. ' +
          'Consider splitting into smaller, focused components.'
      )
    }

    expect(actionableHandlers).toHaveLength(0)
  })

  it('should enforce import count limits', () => {
    const excessiveImports: ComponentMetrics[] = []

    for (const file of componentFiles) {
      const metrics = analyzeComponent(file)
      if (metrics.imports > MAX_COMPONENT_IMPORTS) {
        excessiveImports.push(metrics)
      }
    }

    const actionableImports = filterAllowed(excessiveImports)

    if (actionableImports.length > 0) {
      const report = actionableImports
        .map((m) => {
          const relativePath = relativeToWebRoot(m.filePath)
          return `${relativePath}: ${m.imports} imports`
        })
        .join('\n')

      throw new Error(
        `Found ${actionableImports.length} components with too many imports:\n${report}\n\n` +
          'Components with many dependencies may indicate multiple responsibilities. ' +
          'Consider splitting into smaller, focused components.'
      )
    }

    expect(actionableImports).toHaveLength(0)
  })
})
