import StyleDictionary from 'style-dictionary';
import fs from 'fs';
import path from 'path';

// Register a custom transform for Dart (Flutter)
StyleDictionary.registerTransform({
  name: 'size/flutter/sp',
  type: 'value',
  filter: function(prop) {
    return prop.attributes.category === 'font' && prop.attributes.type === 'size';
  },
  transform: function(prop) {
    return parseFloat(prop.original.value) + '.sp';
  }
});

StyleDictionary.registerFormat({
  name: 'vscode/theme',
  format: function({ dictionary }) {
    const colors = {};
    dictionary.allTokens.forEach(token => {
      // Map token to VS Code color key, assuming we structure it appropriately
      // For simplicity, we just dump them flat for testing, or map specific ones
      // E.g., `vscode.editor.background`
      if (token.path[0] === 'vscode') {
        const key = token.path.slice(1).join('.');
        colors[key] = token.value;
      }
    });

    return JSON.stringify({
      name: "SupremeAI Theme",
      type: "dark",
      colors: colors,
      tokenColors: []
    }, null, 2);
  }
});

StyleDictionary.registerFormat({
  name: 'flutter/custom',
  format: function({ dictionary }) {
    let output = "import 'dart:ui';\n\nclass AppColors {\n  AppColors._();\n\n";
    dictionary.allTokens.forEach(token => {
      if (token.path[0] !== 'vscode') {
        const name = token.name;
        // Convert hex #RRGGBB to 0xFFRRGGBB
        let value = token.value;
        if (typeof value === 'string' && value.startsWith('#')) {
          value = `Color(0xFF${value.substring(1)})`;
        } else if (typeof value === 'string' && value.startsWith('rgba(')) {
          // বাংলা মন্তব্য: CSS rgba() → Dart Color.fromRGBO (অন্যথায় জেনারেটেড Dart invalid হয়)
          const parts = value.replace(/^rgba\(|\)$/g, '').split(',').map((s) => parseFloat(s.trim()));
          value = `Color.fromRGBO(${parts[0]}, ${parts[1]}, ${parts[2]}, ${parts[3]})`;
        }
        output += `  static const ${name} = ${value};\n`;
      }
    });
    output += "}\n";
    return output;
  }
});

const baseDir = (import.meta.dirname || path.dirname(new URL(import.meta.url).pathname)).replace(/\\/g, '/');

const sd = new StyleDictionary({
  source: [`${baseDir}/tokens/**/*.json`],
  platforms: {
    css: {
      transformGroup: 'css',
      buildPath: `${baseDir}/outputs/css/`,
      files: [{
        destination: 'variables.css',
        format: 'css/variables'
      }]
    },
    json: {
      transformGroup: 'web',
      buildPath: path.join(baseDir, 'outputs/json/'),
      files: [{
        destination: 'tokens.json',
        format: 'json/flat'
      }]
    },
    flutter: {
      transformGroup: 'flutter',
      buildPath: path.join(baseDir, 'outputs/flutter/'),
      files: [{
        destination: 'colors.dart',
        format: 'flutter/custom'
      }]
    },
    vscode: {
      transformGroup: 'web',
      buildPath: path.join(baseDir, 'outputs/vscode/'),
      files: [{
        destination: 'supremeai-theme.json',
        format: 'vscode/theme'
      }]
    }
  }
});

sd.buildAllPlatforms();
console.log('Design tokens generated successfully!');

