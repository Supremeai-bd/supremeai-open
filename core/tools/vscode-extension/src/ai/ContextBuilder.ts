import * as vscode from 'vscode';
import * as path from 'path';

export interface AIContext {
  language: string;
  filePath: string;
  fileName: string;
  projectRoot: string;
  openFiles: string[];
  currentFileContent: string;
  selectedText: string;
  cursorPosition: vscode.Position | null;
  imports: string[];
  exports: string[];
  dependencies: string[];
}

export class ContextBuilder {
  async buildContext(document: vscode.TextDocument): Promise<AIContext> {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    const projectRoot = workspaceFolders?.[0]?.uri.fsPath || '';

    const openTexts = vscode.window.visibleTextEditors
      .filter(editor => editor.document.languageId === document.languageId)
      .map(editor => editor.document.uri.fsPath);

    const currentContent = document.getText();
    const imports = this.extractImports(currentContent, document.languageId);
    const exports = this.extractExports(currentContent, document.languageId);
    const dependencies = await this.extractDependencies(projectRoot);

    const activeEditor = vscode.window.activeTextEditor;
    const selectedText = activeEditor?.selection
      ? document.getText(activeEditor.selection)
      : '';

    return {
      language: document.languageId,
      filePath: document.uri.fsPath,
      fileName: document.fileName,
      projectRoot,
      openFiles: openTexts,
      currentFileContent: currentContent,
      selectedText,
      cursorPosition: activeEditor?.selection?.active || null,
      imports,
      exports,
      dependencies,
    };
  }

  buildMemoryPrompt(context: AIContext, memoryContext: string = ''): string {
    return `${memoryContext ? `[Memory Context]\n${memoryContext}\n\n` : ''}[Current File Context]
- Language: ${context.language}
- File: ${context.fileName}
- Project: ${context.projectRoot || 'Unknown'}
- Imports: ${context.imports.slice(0, 5).join(', ')}
- Selected: ${context.selectedText.slice(0, 200)}

[currentFileContent]
${context.currentFileContent.slice(0, 4000)}`;
  }

  extractImports(code: string, language: string): string[] {
    const imports: string[] = [];

    if (language === 'typescript' || language === 'javascript') {
      const importRegex = /import\s+.*\s+from\s+['"]([^'"]+)['"]/g;
      let match;
      while ((match = importRegex.exec(code)) !== null) {
        imports.push(match[1]);
      }
    } else if (language === 'python') {
      const importRegex = /^(?:import|from)\s+([^\s]+)/gm;
      let match;
      while ((match = importRegex.exec(code)) !== null) {
        imports.push(match[1]);
      }
    }

    return imports;
  }

  extractExports(code: string, language: string): string[] {
    const exports: string[] = [];

    if (language === 'typescript' || language === 'javascript') {
      const exportRegex = /export\s+(?:default\s+)?(?:class|function|const|let|var)\s+(\w+)/g;
      let match;
      while ((match = exportRegex.exec(code)) !== null) {
        exports.push(match[1]);
      }
    }

    return exports;
  }

  private async extractDependencies(projectRoot: string): Promise<string[]> {
    const deps: string[] = [];

    if (!projectRoot) { return deps; }

    try {
      const packageJsonPath = path.join(projectRoot, 'package.json');
      // Dynamic require bundler-এ কাজ করে না — fs.readFileSync + JSON.parse ব্যবহার করা হলো
      const fs = await import('fs');
      const fileContent = fs.readFileSync(packageJsonPath, 'utf8');
      const packageJson = JSON.parse(fileContent);

      const allDeps = {
        ...packageJson.dependencies,
        ...packageJson.devDependencies,
      };

      return Object.keys(allDeps);
    } catch {
      return deps;
    }
  }

  buildPrompt(context: AIContext, userPrompt: string): string {
    return `Context:
- Language: ${context.language}
- File: ${context.fileName}
- Project: ${context.projectRoot || 'Unknown'}
- Imports: ${context.imports.slice(0, 5).join(', ')}
- Selected: ${context.selectedText.slice(0, 200)}

Prompt: ${userPrompt}`;
  }
}
