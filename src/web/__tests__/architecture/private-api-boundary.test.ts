import { describe, expect, it } from '@jest/globals'
import * as fs from 'fs'
import * as path from 'path'
import * as ts from 'typescript'

const WEB_ROOT = path.join(__dirname, '../..')
const SEARCH_ROOTS = [
  path.join(WEB_ROOT, 'app'),
  path.join(WEB_ROOT, 'components'),
]

function findSourceFiles(dir: string): string[] {
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
      entry.name !== '__tests__' &&
      entry.name !== '__mocks__' &&
      entry.name !== 'node_modules'
    ) {
      files.push(...findSourceFiles(fullPath))
      continue
    }
    if (
      entry.isFile() &&
      (entry.name.endsWith('.ts') || entry.name.endsWith('.tsx')) &&
      !entry.name.includes('.test.') &&
      !entry.name.includes('.spec.')
    ) {
      files.push(fullPath)
    }
  }

  return files
}

function isUseClientFile(source: string): boolean {
  return /^['"]use client['"]/.test(source.trim())
}

function isTypeOnlyImportDeclaration(statement: ts.ImportDeclaration): boolean {
  const importClause = statement.importClause
  if (!importClause) {
    return true
  }
  if (importClause.isTypeOnly) {
    return true
  }
  if (importClause.name) {
    return false
  }
  if (!importClause.namedBindings) {
    return false
  }
  if (ts.isNamespaceImport(importClause.namedBindings)) {
    return false
  }
  return importClause.namedBindings.elements.every((element) => element.isTypeOnly)
}

describe('Private API boundary', () => {
  it('forbids runtime @/lib/api imports from use client files', () => {
    const violations: string[] = []
    const files = SEARCH_ROOTS.flatMap((root) => findSourceFiles(root))

    for (const filePath of files) {
      const source = fs.readFileSync(filePath, 'utf8')
      if (!isUseClientFile(source)) {
        continue
      }

      const sourceFile = ts.createSourceFile(
        filePath,
        source,
        ts.ScriptTarget.Latest,
        true,
        filePath.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
      )

      for (const statement of sourceFile.statements) {
        if (!ts.isImportDeclaration(statement)) {
          continue
        }
        const moduleSpecifier = statement.moduleSpecifier
        if (!ts.isStringLiteral(moduleSpecifier)) {
          continue
        }
        if (!moduleSpecifier.text.startsWith('@/lib/api/')) {
          continue
        }
        if (!isTypeOnlyImportDeclaration(statement)) {
          violations.push(
            `${path.relative(WEB_ROOT, filePath)} imports runtime API symbols from ${moduleSpecifier.text}`,
          )
        }
      }
    }

    expect(violations).toEqual([])
  })
})
