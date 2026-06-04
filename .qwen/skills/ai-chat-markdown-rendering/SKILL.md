---
name: ai-chat-markdown-rendering
description: Render AI markdown responses (bold, italic, newlines) as formatted HTML in vanilla JS frontend — convert on client side, not server side, to avoid JSON serialization issues
source: auto-skill
extracted_at: '2026-06-04T12:26:05.890Z'
---

# Rendering AI Markdown in Vanilla JS Chat UIs

## The problem

AI models (GigaChat, ChatGPT, etc.) return markdown formatting (`**bold**`, `*italic*`, `\n`) in their responses even when the system prompt asks them not to. A vanilla JS frontend using `textContent` displays raw markdown asterisks as visible text. Switching to `innerHTML` with backend-converted HTML doesn't work reliably because JSON serialization can escape `<` as `\u003c`, causing HTML tags to appear as literal text inside the div ("everything ends up in quotes").

## The fix: convert markdown → HTML on the frontend, NOT the backend

### Why backend conversion fails

When you convert `**bold**` → `<strong>bold</strong>` on the backend and return it via JSON API, the HTML tags pass through JSON serialization → HTTP transfer → `JSON.parse()` → variable assignment → `innerHTML`. At some point in this chain, `<` characters may get escaped or mangled, resulting in the browser showing `<strong>bold</strong>` as visible text instead of rendering bold.

### Why frontend conversion works

By keeping the backend response as raw markdown and converting to HTML in JavaScript, you bypass all serialization issues. The JS regex operates directly on the string in the browser's memory, and `innerHTML` receives a clean HTML string that it can render immediately.

## Implementation pattern

### Backend: return raw markdown, no conversion

```python
# services/chat_service.py — just return the AI's raw response
return reply  # raw markdown, NOT converted to HTML
```

### Frontend: JS conversion function + innerHTML

```javascript
function mdToHtml(s){
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');
  s = s.replace(/\n/g, '<br>');
  return s;
}
```

### Rendering the bubble

```javascript
// Render formatted HTML in the UI bubble
b.innerHTML = mdToHtml(reply);

// Store RAW markdown in chat history (for AI context on next request)
aiHistory.push({ role:'assistant', content:reply });
```

## Critical: store raw markdown in AI history, HTML only in UI

When the user sends a follow-up message, the chat history is sent back to the AI. If you store HTML (`<strong>bold</strong>`) in `aiHistory`, the AI sees HTML tags in its conversation context and may:
- Start outputting HTML instead of markdown
- Get confused by tag syntax
- Break its response format

Always store the **raw markdown** reply in `aiHistory`, and use the **HTML-converted** version only for `innerHTML` rendering.

## Regex ordering matters

Process `**bold**` BEFORE `*italic*` — the bold regex must run first, otherwise the italic regex would match the inner `*` characters of `**bold**` and produce broken output like `<em><em>bold</em></em>`.

## Minimal conversion is best

Only convert the markdown constructs your AI actually uses. GigaChat typically uses `**bold**`, `*italic*`, and newlines. Don't build a full markdown parser — it's overkill for chat bubbles and introduces edge-case bugs. Keep it to inline formatting + line breaks.