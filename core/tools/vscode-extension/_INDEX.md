# tools/vscode-extension/ — File Index
> AI: Extension = 100% Thin Client। কোনো LLM logic এখানে থাকবে না।

## Key Files
| File | কী করে | Status |
|---|---|---|
| `src/services/SupremeAIService.ts` | Backend API communication layer | OK (100% Thin-Client, Ollama offline fallback only) |
| `src/extension.ts` | Extension entry point, command registration | OK |
| `src/providers/SwarmPipelineProvider.ts` | `/api/chat/stream` SSE handler | OK |
| `package.json` | VS Code manifest, commands, settings | OK |

## Architecture Rule
```
User → Extension (Thin Client) → SupremeAI Backend → [LLM providers hidden]
                                      ↑
                          শুধু এখানেই সব intelligence
```

## Status
- `SupremeAIService.ts`: OpenRouter fetch logic অপসারিত এবং ১০০% Thin Client নিশ্চিত করা হয়েছে ✅
- Brand: GPT/OpenRouter/Groq নাম extension UI-তে সম্পূর্ণ নিষিদ্ধ ✅
