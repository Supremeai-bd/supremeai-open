// Web Worker for parsing large JSON/log data without blocking main thread
self.onmessage = function(e) {
  const { action, data } = e.data;

  switch (action) {
    case 'PARSE_LOGS': {
      const lines = data.split('\n');
      const parsed = lines.map((line: string, index: number) => {
        try {
          if (line.includes('"') && line.includes(',')) {
            return JSON.parse(line);
          }
          return { raw: line, lineNumber: index };
        } catch {
          return { raw: line, lineNumber: index };
        }
      }).filter(Boolean);
      self.postMessage({ action: 'LOGS_PARSED', result: parsed });
      break;
    }

    case 'PARSE_LARGE_JSON':
      try {
        const parsed = JSON.parse(data);
        self.postMessage({ action: 'JSON_PARSED', result: parsed });
      } catch (err) {
        self.postMessage({ action: 'PARSE_ERROR', error: err instanceof Error ? err.message : String(err) });
      }
      break;

    case 'SEARCH_LOGS': {
      const { logs, query } = e.data.payload;
      interface LogItem {
        raw?: string;
        message?: string;
      }
      const results = (logs as LogItem[]).filter((log: LogItem) =>
        log.raw?.toLowerCase().includes(query.toLowerCase()) ||
        log.message?.toLowerCase().includes(query.toLowerCase())
      );
      self.postMessage({ action: 'SEARCH_RESULTS', result: results });
      break;
    }

    case 'FILTER_LOGS': {
      // বাংলা মন্তব্য: LiveLogs কম্পোনেন্টের filter/search লজিক এখানে অফলোড করা হয়েছে
      // যাতে বড় লগ অ্যারের ওপর main thread block না হয়।
      const { logs, level, searchTerm } = e.data.payload;
      const term = (searchTerm || '').toLowerCase();
      const filtered = (logs as string[]).filter((log: string) => {
        const up = log.toUpperCase();
        const matchesSearch = log.toLowerCase().includes(term);
        if (level === 'ALL') return matchesSearch;
        if (level === 'INFO') return matchesSearch && up.includes('INFO');
        if (level === 'WARN') return matchesSearch && (up.includes('WARN') || up.includes('WARNING'));
        if (level === 'ERROR') return matchesSearch && (up.includes('ERROR') || up.includes('ERR') || up.includes('FAIL'));
        return matchesSearch;
      });
      self.postMessage({ action: 'FILTERED_LOGS', result: filtered });
      break;
    }

    default:
      self.postMessage({ action: 'UNKNOWN', error: 'Unknown action: ' + action });
  }
};
